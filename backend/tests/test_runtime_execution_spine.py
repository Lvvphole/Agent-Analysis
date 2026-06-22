"""Runtime execution spine tests (handoff Sections 16, 18).

Proves POST /runs -> POST /runs/{id}/chain/execute -> GET results runs the
AI_READINESS_AUDIT chain end-to-end through the runtime: workspace policy,
controlled tools, a controlled model provider, quarantine, structured parsing,
hashed evidence, independent verifier, and a real ChainExecutionResult — with no
merge, deploy, or PR, and no repo mutation.
"""

from __future__ import annotations

import glob
import json
import os

import pytest

from app.agents.manual_provider import ManualAnalysisAdapter
from app.agents.provider import AgentRuntimeConfig
from app.chains.context import snapshot_repo
from app.chains.registry import CHAIN_DEFINITIONS
from app.constants import Decision
from app.runtime.runtime_executor import (
    RuntimeExecutor,
    build_runtime_executor,
    configure,
    fake_analysis_config,
    get_settings,
)
from app.runtime.workspace_policy import WorkspacePolicy, WorkspacePolicyError
from app.schemas.model_policy import ModelRole, ModelSpec

from tests.conftest import make_chain_request

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.store import registry  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


# --- helpers ----------------------------------------------------------------

def _direct_executor(tmp_path, *, agent_config=None):
    return RuntimeExecutor(
        workspace_policy=WorkspacePolicy(tmp_path),
        artifacts_root=tmp_path / "artifacts",
        agent_config=agent_config if agent_config is not None else fake_analysis_config(),
    )


@pytest.fixture(autouse=True)
def _clear_runs():
    registry.runs.clear()
    yield
    registry.runs.clear()


@pytest.fixture
def restore_settings():
    s = get_settings()
    saved = (s.workspace_root, s.artifacts_root, s.provider_mode)
    yield
    s.workspace_root, s.artifacts_root, s.provider_mode = saved


# --- direct RuntimeExecutor (no API) ---------------------------------------

def test_executes_ai_readiness_end_to_end(temp_repo, tmp_path):
    result = _direct_executor(tmp_path).execute(
        make_chain_request(), execution_path=str(temp_repo)
    )
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    assert result.chain_id == "ai_readiness_audit_chain"
    assert result.verifier_decision == Decision.PASS
    assert result.auto_merge is False and result.auto_deploy is False

    run_dir = tmp_path / "artifacts" / "run-1"
    # Deterministic + agent + tool artifacts all present.
    for name in (
        "repo_tree.log",
        "codebase_ai_readiness_report.json",
        "verifier_report.json",
        "tool_list_repo_tree.log",
        "raw_agent_output.log",
        "agent_summary.md",
        "structured_agent_output.json",
    ):
        assert (run_dir / name).exists(), name


def test_agent_output_quarantined_and_not_evidence(temp_repo, tmp_path):
    _direct_executor(tmp_path).execute(make_chain_request(), execution_path=str(temp_repo))
    run_dir = tmp_path / "artifacts" / "run-1"
    inv_files = glob.glob(str(run_dir / "llm_invocation_*.json"))
    assert inv_files, "model invocation record must be written"
    record = json.loads(open(inv_files[0]).read())
    assert record["used_as_evidence"] is False
    assert record["request_hash"] and record["response_hash"]


def test_handler_order_comes_from_registry(temp_repo, tmp_path):
    result = _direct_executor(tmp_path).execute(make_chain_request(), execution_path=str(temp_repo))
    executed = [h.handler_name for h in result.handler_results]
    expected = list(CHAIN_DEFINITIONS["ai_readiness_audit_chain"].handler_names)
    assert executed == expected


def test_runtime_does_not_mutate_repo(temp_repo, tmp_path):
    before = snapshot_repo(temp_repo)
    _direct_executor(tmp_path).execute(make_chain_request(), execution_path=str(temp_repo))
    assert snapshot_repo(temp_repo) == before


def test_unknown_task_type_blocks(temp_repo, tmp_path):
    request = make_chain_request()
    object.__setattr__(request, "task_type", _FakeTaskType("MYSTERY"))
    result = _direct_executor(tmp_path).execute(request, execution_path=str(temp_repo))
    assert result.final_status == "BLOCKED"


def test_provider_unavailable_blocks(temp_repo, tmp_path):
    spec = ModelSpec(model_id="x-analyst", provider="x", role=ModelRole.ANALYST)
    cfg = AgentRuntimeConfig(specs=[spec], adapters={})  # declared but no adapter
    result = _direct_executor(tmp_path, agent_config=cfg).execute(
        make_chain_request(), execution_path=str(temp_repo)
    )
    assert result.final_status == "BLOCKED"
    agent = next(h for h in result.handler_results if h.handler_name == "AnalysisAgentInvocationHandler")
    assert agent.status.value == "BLOCKED"


def test_malformed_model_output_blocks(temp_repo, tmp_path):
    spec = ModelSpec(model_id="manual-analyst", provider="manual", role=ModelRole.ANALYST)
    cfg = AgentRuntimeConfig(
        specs=[spec],
        adapters={"manual": ManualAnalysisAdapter(outputs={"manual-analyst": "not json"})},
    )
    result = _direct_executor(tmp_path, agent_config=cfg).execute(
        make_chain_request(), execution_path=str(temp_repo)
    )
    assert result.final_status == "BLOCKED"
    parser = next(h for h in result.handler_results if h.handler_name == "StructuredOutputParserHandler")
    assert parser.status.value == "BLOCKED"


def test_evaluator_cannot_override_independent_verifier(temp_repo, tmp_path):
    result = _direct_executor(tmp_path).execute(make_chain_request(), execution_path=str(temp_repo))
    verifier = next(h for h in result.handler_results if h.handler_name == "AnalysisVerifierHandler")
    evaluator = next(h for h in result.handler_results if h.handler_name == "EvaluatorHandler")
    assert verifier.handler_type.value == "VERIFIER"
    assert evaluator.handler_type.value == "EVALUATOR"
    # The evaluator runs after the verifier and cannot change the decision.
    assert result.verifier_decision == Decision.PASS


# --- workspace policy -------------------------------------------------------

def test_workspace_policy_allows_in_root(temp_repo, tmp_path):
    assert WorkspacePolicy(tmp_path).resolve(str(temp_repo)) == temp_repo.resolve()


def test_workspace_policy_blocks_empty(tmp_path):
    with pytest.raises(WorkspacePolicyError):
        WorkspacePolicy(tmp_path).resolve("")


def test_workspace_policy_blocks_outside_root(tmp_path):
    with pytest.raises(WorkspacePolicyError):
        WorkspacePolicy(tmp_path).resolve(os.sep + "etc")


def test_workspace_policy_blocks_nonexistent(tmp_path):
    with pytest.raises(WorkspacePolicyError):
        WorkspacePolicy(tmp_path).resolve(str(tmp_path / "does_not_exist"))


def test_workspace_policy_blocks_nested_duplicate(tmp_path):
    with pytest.raises(WorkspacePolicyError):
        WorkspacePolicy(tmp_path).resolve(str(tmp_path / "agent-analysis" / "agent-analysis"))


# --- API surface ------------------------------------------------------------

def _create_run(run_id="run-rt"):
    from tests.conftest import make_manifest

    resp = client.post("/runs", json=make_manifest(run_id=run_id).model_dump(mode="json"))
    assert resp.status_code == 201, resp.text
    return run_id


def _execute_body(run_id, repo, **req_overrides):
    req = make_chain_request(run_id=run_id, task_id="task-1", **req_overrides)
    return {"request": req.model_dump(mode="json"), "execution_path": str(repo)}


def test_api_execute_and_results(temp_repo, tmp_path, restore_settings):
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run()
    resp = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body(run_id, temp_repo))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["final_status"] == "PASS"
    assert body["chain_id"] == "ai_readiness_audit_chain"
    assert body["auto_merge"] is False and body["auto_deploy"] is False

    # Results endpoint returns the actual stored ChainExecutionResult.
    got = client.get(f"/runs/{run_id}/chain/results")
    assert got.status_code == 200
    assert got.json()["final_status"] == "PASS"
    assert got.json()["verifier_decision"] == "PASS"


def test_api_execute_arbitrary_path_blocks(temp_repo, tmp_path, restore_settings):
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run()
    body = _execute_body(run_id, temp_repo)
    body["execution_path"] = os.sep + "etc"  # outside the allowed workspace
    resp = client.post(f"/runs/{run_id}/chain/execute", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_status"] == "BLOCKED"


def test_api_execute_unknown_run_404(temp_repo):
    body = _execute_body("nope", temp_repo)
    assert client.post("/runs/nope/chain/execute", json=body).status_code == 404


def test_no_forbidden_endpoints_present():
    paths = list(client.get("/openapi.json").json()["paths"].keys())
    assert "/runs/{run_id}/chain/execute" in paths
    forbidden = (
        "complete", "merge", "deploy", "bypass", "force-pass", "approve",
        "ship", "release", "publish", "promote", "finish", "mark-done", "force", "admin",
    )
    for path in paths:
        assert not any(f in path for f in forbidden), path


class _FakeTaskType:
    def __init__(self, value):
        self.value = value
