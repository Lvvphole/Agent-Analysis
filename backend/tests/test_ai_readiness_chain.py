"""AI Readiness chain end-to-end tests (handoff Section 11.1, 16.4)."""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.chains.context import snapshot_repo
from app.constants import Decision

from tests.conftest import make_chain_request


def _run(store, repo):
    return ChainExecutor().execute(make_chain_request(), store=store, repo_fs_path=repo)


def test_ai_readiness_uses_read_only_chain(temp_repo, artifact_store):
    result = _run(artifact_store, temp_repo)
    assert result.chain_id == "ai_readiness_audit_chain"
    assert result.mode.value == "READ_ONLY_ANALYSIS"


def test_ai_readiness_passes_without_diff(temp_repo, artifact_store):
    result = _run(artifact_store, temp_repo)
    assert result.final_status == "PASS"
    assert result.verifier_decision == Decision.PASS
    # No diff.patch is produced or required.
    assert not (artifact_store.run_dir("run-1") / "diff.patch").exists()


def test_ai_readiness_does_not_mutate_repo(temp_repo, artifact_store):
    before = snapshot_repo(temp_repo)
    _run(artifact_store, temp_repo)
    assert snapshot_repo(temp_repo) == before


def test_ai_readiness_fails_if_repo_modified(temp_repo, artifact_store):
    """If a handler mutated the repo, ReadOnlyComplianceHandler must FAIL."""
    from app.chains.context import ChainContext
    from app.handlers.analysis import ReadOnlyComplianceHandler
    from app.storage.evidence_writer import EvidenceLedgerWriter

    request = make_chain_request()
    ctx = ChainContext(
        request=request,
        store=artifact_store,
        evidence=EvidenceLedgerWriter(task_id="task-1", run_id="run-1"),
        repo_fs_path=temp_repo,
        repo_snapshot=snapshot_repo(temp_repo),
    )
    (temp_repo / "new_file.py").write_text("y=2\n")  # simulate mutation
    result = ReadOnlyComplianceHandler().handle(request, ctx)
    assert result.status.value == "FAIL"
    assert any("modified repository" in r for r in result.failure_reasons)


def test_ai_readiness_requires_evidence_ledger(temp_repo, artifact_store):
    result = _run(artifact_store, temp_repo)
    # The evidence ledger was finalized and every entry is hashed.
    ledger_path = artifact_store.run_dir("run-1")
    assert (ledger_path / "repo_tree.log").exists()
    assert (ledger_path / "codebase_ai_readiness_report.json").exists()
    # EvidenceGateHandler passed (it requires an ANALYSIS_REPORT artifact).
    names = [h.handler_name for h in result.handler_results]
    assert "EvidenceGateHandler" in names


def test_ai_readiness_runs_independent_analysis_verifier(temp_repo, artifact_store):
    result = _run(artifact_store, temp_repo)
    verifier = next(
        h for h in result.handler_results if h.handler_name == "AnalysisVerifierHandler"
    )
    assert verifier.handler_type.value == "VERIFIER"
    assert verifier.status.value == "PASS"
    assert (artifact_store.run_dir("run-1") / "verifier_report.json").exists()


def test_unknown_task_type_blocks(temp_repo, artifact_store):
    # Build a request with a known enum then force an unregistered task value.
    request = make_chain_request()
    object.__setattr__(request, "task_type", _FakeTaskType("MYSTERY"))
    result = ChainExecutor().execute(request, store=artifact_store, repo_fs_path=temp_repo)
    assert result.final_status == "BLOCKED"


class _FakeTaskType:
    def __init__(self, value):
        self.value = value
