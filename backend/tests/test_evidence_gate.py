"""Evidence gate tests (Sections 13.3, 6.2, 19)."""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.evidence_gate import evidence_gate
from app.schemas.evidence_ledger import LedgerEntry

from tests.conftest import make_ledger


def _gate(ledger, **kw):
    return evidence_gate(ledger, run_id="run-1", task_id="task-1", **kw)


def test_valid_ledger_passes():
    assert _gate(make_ledger()).status == GateStatus.PASS


def test_unhashed_artifact_rejected():
    ledger = make_ledger(
        ledger_entries=[
            LedgerEntry(
                entry_id="E1",
                artifact_type="DIFF",
                artifact_path="artifacts/run-1/diff.patch",
                hash="",  # missing hash
            )
        ]
    )
    result = _gate(ledger)
    assert result.status == GateStatus.FAIL
    assert any("artifact hash missing" in r for r in result.reasons)


def test_missing_required_artifact_rejected():
    result = _gate(make_ledger(), required_artifact_types=["VERIFIER_REPORT"])
    assert any("required artifact missing: VERIFIER_REPORT" in r for r in result.reasons)


def test_agent_summary_used_as_proof_rejected():
    ledger = make_ledger(
        ledger_entries=[
            LedgerEntry(
                entry_id="E1",
                artifact_type="COMMAND_OUTPUT",
                artifact_path="artifacts/run-1/agent_summary.md",
                hash="c" * 64,
            )
        ]
    )
    result = _gate(ledger)
    assert result.status == GateStatus.FAIL
    assert any("agent summary used as proof" in r for r in result.reasons)


def test_self_certification_flag_rejected():
    result = _gate(make_ledger(agent_self_certification_used=True))
    assert "agent self-certification used as evidence" in result.reasons


def test_ledger_not_linked_to_run_rejected():
    ledger = make_ledger(run_id="other-run")
    result = evidence_gate(ledger, run_id="run-1", task_id="task-1")
    assert any("ledger not linked to run_id" in r for r in result.reasons)


def test_command_claimed_without_output_rejected():
    ledger = make_ledger(
        ledger_entries=[
            LedgerEntry(
                entry_id="E1",
                artifact_type="COMMAND_OUTPUT",
                artifact_path="",  # claimed command but no captured output
                command="python -m pytest",
                hash="d" * 64,
            )
        ]
    )
    result = _gate(ledger)
    assert any("command output missing" in r for r in result.reasons)


def test_in_place_mutation_rejected():
    ledger = make_ledger(
        ledger_entries=[
            LedgerEntry(entry_id="E1", artifact_type="DIFF", artifact_path="d", hash="1" * 64),
            LedgerEntry(entry_id="E1", artifact_type="TEST", artifact_path="t", hash="2" * 64),
        ]
    )
    result = _gate(ledger)
    assert any("mutated in place" in r for r in result.reasons)
