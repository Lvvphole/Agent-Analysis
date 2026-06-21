"""No-self-certification gate (Section 13.7).

The agent that creates work can never be the authority that certifies it.
"""

from __future__ import annotations

from app.constants import Decision
from app.schemas.gate_result import GateResult

GATE_NAME = "no_self_certification_gate"


def no_self_certification_gate(
    *,
    coding_agent_run_id: str,
    verifier_run_id: str,
    coding_agent_id: str = "",
    verifier_id: str = "",
    verifier_decision: Decision = Decision.PENDING,
    agent_summary_used_as_evidence: bool = False,
    executor_marked_done: bool = False,
) -> GateResult:
    """Return PASS only if creation and certification are independent."""
    reasons: list[str] = []

    if (
        coding_agent_run_id
        and verifier_run_id
        and coding_agent_run_id == verifier_run_id
    ):
        reasons.append("coding_agent_run_id == verifier_run_id")

    if coding_agent_id and verifier_id and coding_agent_id == verifier_id:
        reasons.append("same agent creates and certifies work")

    if agent_summary_used_as_evidence:
        reasons.append("agent summary used as evidence")

    if executor_marked_done and verifier_decision != Decision.PASS:
        reasons.append("executor marks Done without verifier PASS")

    return GateResult.of(GATE_NAME, reasons)
