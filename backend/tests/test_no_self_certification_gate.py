"""No-self-certification gate tests (Sections 13.7, 6.3, 19)."""

from __future__ import annotations

from app.constants import Decision, GateStatus
from app.gates.no_self_certification_gate import no_self_certification_gate


def test_independent_runs_pass():
    result = no_self_certification_gate(
        coding_agent_run_id="car-1",
        verifier_run_id="vr-1",
        coding_agent_id="agent",
        verifier_id="verifier",
        verifier_decision=Decision.PASS,
    )
    assert result.status == GateStatus.PASS


def test_same_run_id_fails():
    result = no_self_certification_gate(
        coding_agent_run_id="same", verifier_run_id="same"
    )
    assert result.status == GateStatus.FAIL
    assert "coding_agent_run_id == verifier_run_id" in result.reasons


def test_same_agent_identity_fails():
    result = no_self_certification_gate(
        coding_agent_run_id="car-1",
        verifier_run_id="vr-1",
        coding_agent_id="x",
        verifier_id="x",
    )
    assert "same agent creates and certifies work" in result.reasons


def test_agent_summary_as_evidence_fails():
    result = no_self_certification_gate(
        coding_agent_run_id="car-1",
        verifier_run_id="vr-1",
        agent_summary_used_as_evidence=True,
    )
    assert "agent summary used as evidence" in result.reasons


def test_executor_marks_done_without_pass_fails():
    result = no_self_certification_gate(
        coding_agent_run_id="car-1",
        verifier_run_id="vr-1",
        verifier_decision=Decision.PENDING,
        executor_marked_done=True,
    )
    assert "executor marks Done without verifier PASS" in result.reasons
