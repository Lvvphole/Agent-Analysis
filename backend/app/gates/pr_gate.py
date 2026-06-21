"""PR gate (Section 13.8).

The release boundary. Verifier PASS may allow a gated PR; it never allows
merge or deploy, and the loop never crosses into a protected branch.
"""

from __future__ import annotations

from app.constants import Decision
from app.schemas.gate_result import GateResult

GATE_NAME = "pr_gate"


def pr_gate(
    *,
    verifier_decision: Decision,
    pr_url: str = "",
    pr_skip_reason: str = "",
    auto_merge: bool = False,
    auto_deploy: bool = False,
    merge_occurred: bool = False,
    deploy_occurred: bool = False,
    pushed_to_protected_branch: bool = False,
) -> GateResult:
    """Return PASS only if the PR stays gated and nothing merged or deployed."""
    reasons: list[str] = []

    if auto_merge:
        reasons.append("auto_merge must be false")
    if auto_deploy:
        reasons.append("auto_deploy must be false")
    if merge_occurred:
        reasons.append("merge occurred inside autonomous loop")
    if deploy_occurred:
        reasons.append("deploy occurred inside autonomous loop")
    if pushed_to_protected_branch:
        reasons.append("PR bypasses protected branch rules")

    if (
        verifier_decision == Decision.PASS
        and not pr_url
        and not pr_skip_reason
    ):
        reasons.append("PR missing after verifier PASS without documented reason")

    return GateResult.of(GATE_NAME, reasons)
