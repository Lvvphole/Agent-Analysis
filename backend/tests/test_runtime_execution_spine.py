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

from app.api.store import get_repository, registry  # noqa: E402
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
    saved = (s.workspace_root, s.artifacts_root, s.provider_mode, s.production_mode)
    yield
    (s.workspace_root, s.artifacts_root, s.provider_mode, s.production_mode) = saved


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


def test_api_responses_do_not_leak_artifact_paths(git_repo, tmp_path, restore_settings):
    """artifacts_created/evidence_refs carry absolute host paths and must not
    appear in the execute or results responses (the durable evidence_artifacts
    table is the audit record; runs.snapshot keeps the full result internally)."""
    configure(workspace_root=git_repo, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-leak2")
    execute = client.post(
        f"/runs/{run_id}/chain/execute", json=_execute_body("run-leak2", git_repo)
    )
    assert execute.status_code == 200, execute.text
    results = client.get(f"/runs/{run_id}/chain/results")
    assert results.status_code == 200

    artifacts_root = str(get_settings().artifacts_root.resolve())
    for resp in (execute, results):
        assert artifacts_root not in resp.text
        handler_results = resp.json()["handler_results"]
        assert handler_results, "expected at least one handler result"
        # The path-bearing fields are stripped from the API surface entirely.
        for hr in handler_results:
            assert "artifacts_created" not in hr
            assert "evidence_refs" not in hr


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


def test_execute_rejects_run_id_mismatch(temp_repo, tmp_path, restore_settings):
    # body.request.run_id diverges from the URL run_id -> 422, no execution.
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-url")
    body = _execute_body("run-url", temp_repo)
    body["request"]["run_id"] = "run-evil"  # divergent identity
    resp = client.post(f"/runs/{run_id}/chain/execute", json=body)
    assert resp.status_code == 422, resp.text
    assert "identity_mismatch" in resp.json()["detail"]
    # No artifacts written under the divergent body run id.
    assert not (tmp_path / "art" / "run-evil").exists()


def test_execute_rejects_task_id_mismatch(temp_repo, tmp_path, restore_settings):
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-tid")  # manifest task_id defaults to "task-1"
    body = _execute_body("run-tid", temp_repo)
    body["request"]["task_id"] = "task-OTHER"  # diverges from registered task_id
    resp = client.post(f"/runs/{run_id}/chain/execute", json=body)
    assert resp.status_code == 422, resp.text
    assert "identity_mismatch" in resp.json()["detail"]


def test_execute_empty_run_id_is_bound_to_url(temp_repo, tmp_path, restore_settings):
    # Empty body run_id is adopted from the URL; execution proceeds and the
    # result/artifacts use the URL run id.
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-bind")
    body = _execute_body("run-bind", temp_repo)
    body["request"]["run_id"] = ""  # server should adopt the URL run_id
    resp = client.post(f"/runs/{run_id}/chain/execute", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_status"] == "PASS"
    assert resp.json()["run_id"] == "run-bind"
    assert (tmp_path / "art" / "run-bind").exists()


def test_execute_matching_run_id_executes(temp_repo, tmp_path, restore_settings):
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-match")
    resp = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body("run-match", temp_repo))
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_status"] == "PASS"
    assert resp.json()["run_id"] == "run-match"


# --- per-attempt isolation (Epic 3) ----------------------------------------

def test_execute_records_attempt_with_base_commit(git_repo, tmp_path, restore_settings):
    # workspace_root is the git repo so base_commit is captured from real HEAD.
    configure(workspace_root=git_repo, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-att")
    resp = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body("run-att", git_repo))
    assert resp.status_code == 200, resp.text

    attempts = client.get(f"/runs/{run_id}/attempts").json()
    assert len(attempts) == 1
    att = attempts[0]
    assert att["attempt_id"] == "run-att-a1"
    assert att["attempt_number"] == 1
    assert att["base_commit"] and len(att["base_commit"]) == 40  # real git SHA
    assert att["workspace_id"] == "workspace-run-att-a1"  # opaque, not a host path
    assert att["final_status"] == resp.json()["final_status"]
    # Artifacts are scoped under {run_id}/{attempt_id}/.
    assert (tmp_path / "art" / "run-att" / "run-att-a1").is_dir()


def test_repeated_execute_increments_attempt_number(temp_repo, tmp_path, restore_settings):
    configure(workspace_root=tmp_path, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-retry")
    for _ in range(2):
        resp = client.post(
            f"/runs/{run_id}/chain/execute", json=_execute_body("run-retry", temp_repo)
        )
        assert resp.status_code == 200, resp.text

    attempts = client.get(f"/runs/{run_id}/attempts").json()
    assert [a["attempt_number"] for a in attempts] == [1, 2]
    assert [a["attempt_id"] for a in attempts] == ["run-retry-a1", "run-retry-a2"]
    # temp_repo is not a git repo, so base_commit is unknown but still recorded.
    assert all(a["base_commit"] is None for a in attempts)


def test_production_mode_rejects_caller_execution_path(temp_repo, tmp_path, restore_settings):
    configure(
        workspace_root=tmp_path,
        artifacts_root=tmp_path / "art",
        provider_mode="fake",
        production_mode=True,
    )
    run_id = _create_run("run-prod")
    resp = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body("run-prod", temp_repo))
    assert resp.status_code == 422, resp.text
    assert "caller_execution_path_forbidden" in resp.json()["detail"]
    # Nothing executed and no attempt was recorded.
    assert client.get(f"/runs/{run_id}/attempts").json() == []


def test_production_mode_allocates_server_workspace(temp_repo, tmp_path, restore_settings):
    # No caller path: the server allocates against its own workspace_root.
    configure(
        workspace_root=temp_repo,
        artifacts_root=tmp_path / "art",
        provider_mode="fake",
        production_mode=True,
    )
    run_id = _create_run("run-srv")
    body = _execute_body("run-srv", temp_repo)
    body["execution_path"] = ""  # caller supplies none
    resp = client.post(f"/runs/{run_id}/chain/execute", json=body)
    assert resp.status_code == 200, resp.text
    attempts = client.get(f"/runs/{run_id}/attempts").json()
    assert len(attempts) == 1
    assert attempts[0]["workspace_id"] == "workspace-run-srv-a1"  # opaque, not a host path


def test_attempts_endpoint_does_not_leak_workspace_root(git_repo, tmp_path, restore_settings):
    """The audit endpoint must not expose the host filesystem path it ran against."""
    configure(workspace_root=git_repo, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-leak")
    resp = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body("run-leak", git_repo))
    assert resp.status_code == 200, resp.text

    raw = client.get(f"/runs/{run_id}/attempts")
    # The resolved workspace_root must appear nowhere in the serialized response.
    assert str(get_settings().workspace_root.resolve()) not in raw.text
    workspace_id = raw.json()[0]["workspace_id"]
    assert workspace_id.startswith("workspace-")
    assert not os.path.isabs(workspace_id)


def test_attempts_endpoint_unknown_run_404():
    assert client.get("/runs/nope/attempts").status_code == 404


# --- evidence artifacts (Epic 6) -------------------------------------------

def test_execute_records_evidence_artifacts_with_attempt_link(git_repo, tmp_path, restore_settings):
    """The run's hashed evidence artifacts are captured on the record and tagged
    with the producing attempt, ready for evidence_artifacts projection."""
    configure(workspace_root=git_repo, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-ev")
    resp = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body("run-ev", git_repo))
    assert resp.status_code == 200, resp.text

    record = get_repository().get(run_id)
    assert record.artifacts, "expected evidence artifacts to be recorded"
    # Every artifact links to this run's single attempt and is hashed.
    assert all(a.attempt_id == "run-ev-a1" for a in record.artifacts)
    assert all(len(a.hash) == 64 for a in record.artifacts)


def test_evidence_artifacts_carrier_excluded_from_responses(git_repo, tmp_path, restore_settings):
    """The evidence_artifacts carrier holds Artifact.path (an internal host path),
    so it must never appear in an API response (cf. the workspace_id leak)."""
    configure(workspace_root=git_repo, artifacts_root=tmp_path / "art", provider_mode="fake")
    run_id = _create_run("run-ev2")
    execute = client.post(f"/runs/{run_id}/chain/execute", json=_execute_body("run-ev2", git_repo))
    assert execute.status_code == 200, execute.text
    results = client.get(f"/runs/{run_id}/chain/results")
    assert results.status_code == 200, results.text

    # The carrier is captured on the record but excluded from every response body.
    assert get_repository().get(run_id).artifacts
    for raw in (execute.json(), results.json()):
        assert "evidence_artifacts" not in raw


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
