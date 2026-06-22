"""Implementation chain tests (handoff Section 11.2, 16.5)."""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision
from app.schemas.chain import PrStatus

from tests.conftest import MANUAL_CANDIDATE, STRATEGIC_DESIGN, make_impl_request


def _run(store, repo, metadata):
    return ChainExecutor().execute(
        make_impl_request(metadata=metadata), store=store, repo_fs_path=repo
    )


def test_requires_diff_patch(temp_repo, artifact_store):
    """A candidate with no diff cannot leave DiffCapture: no PASS without a diff."""
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": {**MANUAL_CANDIDATE, "diff": "", "changed_files": []},
        "test_outcomes": [{"command": "pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.final_status == "BLOCKED"
    assert result.verifier_decision != Decision.PASS
    diff_capture = next(
        h for h in result.handler_results if h.handler_name == "DiffCaptureHandler"
    )
    assert diff_capture.status.value == "BLOCKED"
    assert any("diff.patch required" in r for r in diff_capture.failure_reasons)


def test_full_path_creates_only_gated_pr(temp_repo, artifact_store):
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "test_outcomes": [{"command": "python -m pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.final_status == "PASS"
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    # PR stays gated: never merged, never deployed.
    assert result.auto_merge is False
    assert result.auto_deploy is False
    body = (artifact_store.run_dir("run-1") / "pr_body.md").read_text()
    assert "Auto-merge: NO" in body
    assert "Auto-deploy: NO" in body


def test_quarantines_agent_summary(temp_repo, artifact_store):
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "test_outcomes": [{"command": "pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    # The summary is written as context, never appended to the evidence ledger.
    assert (artifact_store.run_dir("run-1") / "agent_summary.md").exists()
    quarantine = next(
        h for h in result.handler_results if h.handler_name == "AgentOutputQuarantineHandler"
    )
    assert quarantine.status.value == "PASS"
    # Evidence gate still passed -> summary was not used as proof.
    assert result.final_status == "PASS"


def test_requires_independent_verifier(temp_repo, artifact_store):
    """Same coding-agent and verifier run id -> verifier FAIL (no PASS)."""
    candidate = {**MANUAL_CANDIDATE, "agent_run_id": "impl-verifier"}  # collide with verifier id
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": candidate,
        "test_outcomes": [{"command": "pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.verifier_decision == Decision.FAIL
    assert result.final_status != "PASS"


def test_failing_tests_block_pass(temp_repo, artifact_store):
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "test_outcomes": [{"command": "pytest", "exit_code": 1}],  # tests failed
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.verifier_decision == Decision.FAIL
    assert result.final_status != "PASS"


def test_tests_not_applicable_with_reason_allowed(temp_repo, artifact_store):
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "tests_not_applicable": True,
        "tests_not_applicable_reason": "pure config change",
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.final_status == "PASS"
    assert result.verifier_decision == Decision.PASS
