"""CI failure-repair chain tests (handoff Section 11.7).

The CI_FAILURE_REPAIR chain reuses the implementation handlers + verifier and
adds four deterministic, no-network steps: parse a caller-supplied CI log,
classify it, reproduce the failure locally, and validate the workflow YAML —
ending, like every chain, in an independent-verifier PASS and a gated PR.
"""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision, RunType
from app.schemas.chain import PrStatus, TaskType

from tests.conftest import MANUAL_CANDIDATE, STRATEGIC_DESIGN, make_chain_request

CI_SCOPE = {"files_in_scope": ["backend/app/**"], "files_out_of_scope": []}
CI_SCRUM = {
    "product_backlog_item_id": "PBI-8",
    "sprint_goal": "repair the failing CI pipeline",
    "sprint_backlog_task_id": "T-8",
    "definition_of_done_version": "dod-v1",
    "acceptance_criteria": ["the previously failing job must pass in CI"],
}

_FAILING_LOG = (
    "Run python -m pytest\n"
    "tests/test_x.py::test_widget FAILED\n"
    "E   AssertionError: expected 2 got 1\n"
    "##[error]Process completed with exit code 1\n"
)


def _ci_repo(tmp_path, *, workflow="on: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"):
    repo = tmp_path / "repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(workflow)
    (repo / "main.py").write_text("print('hi')\n")
    return repo


def _ci_request(metadata):
    return make_chain_request(
        task_type=TaskType.CI_FAILURE_REPAIR,
        mode=RunType.IMPLEMENTATION,
        scope=CI_SCOPE,
        scrum=CI_SCRUM,
        metadata=metadata,
    )


def _run(store, repo, metadata):
    return ChainExecutor().execute(_ci_request(metadata), store=store, repo_fs_path=repo)


def _full_metadata(**overrides):
    meta = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "ci_failure": {"workflow": "ci.yml", "job": "test", "log": _FAILING_LOG},
        "reproduction": {"test_outcomes": [{"command": "pytest -k widget", "exit_code": 1}]},
        "test_outcomes": [{"command": "python -m pytest", "exit_code": 0}],
    }
    meta.update(overrides)
    return meta


def test_full_path_gates_pr(tmp_path, artifact_store):
    repo = _ci_repo(tmp_path)
    result = _run(artifact_store, repo, _full_metadata())
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False
    cls = next(h for h in result.handler_results if h.handler_name == "FailureClassificationHandler")
    assert cls.metadata.get("category") == "TEST"


def test_missing_ci_log_blocks(tmp_path, artifact_store):
    repo = _ci_repo(tmp_path)
    result = _run(artifact_store, repo, _full_metadata(ci_failure={}))
    assert result.final_status == "BLOCKED"
    parser = next(h for h in result.handler_results if h.handler_name == "CIFailureLogParserHandler")
    assert parser.status.value == "BLOCKED"
    assert any("CI failure log required" in r for r in parser.failure_reasons)


def test_unclassifiable_failure_fails(tmp_path, artifact_store):
    repo = _ci_repo(tmp_path)
    log = "Run something\nsome benign output with no recognizable failure marker\n"
    result = _run(artifact_store, repo, _full_metadata(
        ci_failure={"workflow": "ci.yml", "job": "test", "log": log}
    ))
    assert result.final_status != "PASS"
    cls = next(h for h in result.handler_results if h.handler_name == "FailureClassificationHandler")
    assert cls.status.value == "FAIL"
    assert any("unable to classify" in r for r in cls.failure_reasons)


def test_missing_reproduction_blocks(tmp_path, artifact_store):
    repo = _ci_repo(tmp_path)
    meta = _full_metadata()
    del meta["reproduction"]
    result = _run(artifact_store, repo, meta)
    assert result.final_status == "BLOCKED"
    repro = next(h for h in result.handler_results if h.handler_name == "ReproductionHandler")
    assert repro.status.value == "BLOCKED"


def test_non_failing_reproduction_fails(tmp_path, artifact_store):
    repo = _ci_repo(tmp_path)
    result = _run(artifact_store, repo, _full_metadata(
        reproduction={"test_outcomes": [{"command": "pytest -k widget", "exit_code": 0}]}
    ))
    assert result.final_status != "PASS"
    repro = next(h for h in result.handler_results if h.handler_name == "ReproductionHandler")
    assert repro.status.value == "FAIL"


def test_malformed_workflow_yaml_fails(tmp_path, artifact_store):
    # A workflow that is not valid YAML -> CIConfigValidationHandler FAIL.
    repo = _ci_repo(tmp_path, workflow="on: [push]\njobs:\n  test:\n   bad: : : indent\n")
    result = _run(artifact_store, repo, _full_metadata())
    assert result.final_status != "PASS"
    cfg = next(h for h in result.handler_results if h.handler_name == "CIConfigValidationHandler")
    assert cfg.status.value == "FAIL"
    assert any("invalid CI workflow" in r for r in cfg.failure_reasons)


def test_ci_handlers_registered():
    from app.handlers.base import build_default_registry

    registry = build_default_registry()
    for name in (
        "CIFailureLogParserHandler",
        "FailureClassificationHandler",
        "ReproductionHandler",
        "CIConfigValidationHandler",
    ):
        assert registry.has(name), name
