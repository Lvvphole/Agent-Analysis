"""Bug-fix chain tests (handoff Section 11.3).

The BUG_FIX chain reuses the fully-implemented IMPLEMENTATION handlers and adds
one bug-fix-specific precondition: ``FailureReproductionHandler``. A fix must
first reproduce the failure (a failing baseline), then the post-fix tests must
pass, and only an independent verifier can certify — ending in a gated PR.
"""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision, RunType
from app.schemas.chain import PrStatus, TaskType

from tests.conftest import MANUAL_CANDIDATE, STRATEGIC_DESIGN, make_chain_request

BUG_SCOPE = {"files_in_scope": ["backend/app/**"], "files_out_of_scope": []}
BUG_SCRUM = {
    "product_backlog_item_id": "PBI-7",
    "sprint_goal": "fix the reported defect",
    "sprint_backlog_task_id": "T-7",
    "definition_of_done_version": "dod-v1",
    "acceptance_criteria": ["the failing case must return the corrected value"],
}


def _bug_request(metadata):
    return make_chain_request(
        task_type=TaskType.BUG_FIX,
        mode=RunType.IMPLEMENTATION,
        scope=BUG_SCOPE,
        scrum=BUG_SCRUM,
        metadata=metadata,
    )


def _run(store, repo, metadata):
    return ChainExecutor().execute(_bug_request(metadata), store=store, repo_fs_path=repo)


def test_full_path_with_reproduction_gates_pr(temp_repo, artifact_store):
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "reproduction": {"test_outcomes": [{"command": "pytest -k bug", "exit_code": 1}]},
        "test_outcomes": [{"command": "python -m pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False
    repro = next(
        h for h in result.handler_results if h.handler_name == "FailureReproductionHandler"
    )
    assert repro.status.value == "PASS"
    assert repro.metadata.get("reproduced") is True


def test_missing_reproduction_blocks(temp_repo, artifact_store):
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "test_outcomes": [{"command": "python -m pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.final_status == "BLOCKED"
    repro = next(
        h for h in result.handler_results if h.handler_name == "FailureReproductionHandler"
    )
    assert repro.status.value == "BLOCKED"
    assert any("reproduction required" in r for r in repro.failure_reasons)


def test_non_failing_reproduction_fails(temp_repo, artifact_store):
    # A "reproduction" that exits 0 is no reproduction at all -> FAIL, no faking.
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": MANUAL_CANDIDATE,
        "reproduction": {"test_outcomes": [{"command": "pytest -k bug", "exit_code": 0}]},
        "test_outcomes": [{"command": "python -m pytest", "exit_code": 0}],
    }
    result = _run(artifact_store, temp_repo, metadata)
    assert result.final_status != "PASS"
    repro = next(
        h for h in result.handler_results if h.handler_name == "FailureReproductionHandler"
    )
    assert repro.status.value == "FAIL"
    assert any("did not fail" in r for r in repro.failure_reasons)


def test_failure_reproduction_handler_registered():
    from app.handlers.base import build_default_registry

    assert build_default_registry().has("FailureReproductionHandler")
