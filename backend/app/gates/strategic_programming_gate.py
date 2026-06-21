"""Strategic Programming gate (Section 13.6).

"Done requires controlled complexity." This gate fails when the code works but
makes future change harder.
"""

from __future__ import annotations

from app.schemas.gate_result import GateResult
from app.schemas.strategic_programming import StrategicProgramming

GATE_NAME = "strategic_programming_gate"


def strategic_programming_gate(review: StrategicProgramming) -> GateResult:
    """Return PASS only if the design contains complexity rather than spreads it."""
    reasons: list[str] = []

    if not review.responsibility_owner.strip():
        reasons.append("responsibility owner unclear")

    if len(review.design_options) < 2:
        reasons.append("only one design option considered")

    selected = review.selected_design.strip()
    if not selected:
        reasons.append("selected design not justified")
    else:
        match = next(
            (o for o in review.design_options if o.option_id == selected),
            None,
        )
        if match is None:
            reasons.append("selected design not justified")
        elif match.rejected_or_selected.strip().lower() != "selected":
            reasons.append("selected design not justified")
        elif not match.tradeoffs.strip() and not match.summary.strip():
            reasons.append("selected design not justified")

    # Design-smell self-assessment flags (safe default is False).
    if review.introduces_shallow_passthrough:
        reasons.append("shallow pass-through layers introduced")
    if review.complexity_leaks_into_callers:
        reasons.append("complexity leaks into callers")
    if review.error_handling_scattered:
        reasons.append("error handling scattered")
    if review.invalid_states_unhandled:
        reasons.append("invalid states not designed out when possible")
    if review.unjustified_duplication:
        reasons.append("duplication introduced without justification")
    if review.increases_change_amplification:
        reasons.append("avoidable change amplification increased")
    if review.works_but_harder_to_change:
        reasons.append("code works but makes future change harder")

    return GateResult.of(GATE_NAME, reasons)
