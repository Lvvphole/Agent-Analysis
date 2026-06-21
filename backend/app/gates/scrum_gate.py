"""Scrum gate (Section 13.2).

A task cannot enter execution unless it is fully mapped onto Scrum artifacts
and its acceptance criteria are testable.
"""

from __future__ import annotations

from app.schemas.gate_result import GateResult
from app.schemas.scrum_mapping import ScrumMapping

GATE_NAME = "scrum_gate"

# Heuristic markers that an acceptance criterion is testable: it asserts an
# observable, checkable outcome rather than a vague intention.
_TESTABLE_MARKERS = (
    "must",
    "should",
    "returns",
    "fails",
    "passes",
    "rejects",
    "equals",
    "when",
    "then",
    "given",
    "exit code",
    "==",
    "!=",
)


def _is_testable(criterion: str) -> bool:
    text = criterion.strip().lower()
    if len(text) < 3:
        return False
    return any(marker in text for marker in _TESTABLE_MARKERS)


def scrum_gate(
    mapping: ScrumMapping,
    *,
    locked_definition_of_done_version: str | None = None,
) -> GateResult:
    """Return PASS only if the Scrum mapping is complete and testable.

    ``locked_definition_of_done_version`` is the version captured during PLAN.
    If it is provided and differs from the mapping's version, the Definition of
    Done has been changed mid-run, which is forbidden (Section 6.8).
    """
    reasons: list[str] = []

    if not mapping.product_backlog_item_id:
        reasons.append("Product Backlog Item missing")
    if not mapping.sprint_goal:
        reasons.append("Sprint Goal missing")
    if not mapping.sprint_backlog_task_id:
        reasons.append("Sprint Backlog task missing")

    if not mapping.acceptance_criteria:
        reasons.append("acceptance criteria missing")
    elif not all(_is_testable(c) for c in mapping.acceptance_criteria):
        reasons.append("acceptance criteria not testable")

    if not mapping.definition_of_done_version:
        reasons.append("Definition of Done version missing")

    if not mapping.supports_sprint_goal:
        reasons.append("task does not support Sprint Goal")

    if (
        locked_definition_of_done_version is not None
        and mapping.definition_of_done_version
        and mapping.definition_of_done_version
        != locked_definition_of_done_version
    ):
        reasons.append("Definition of Done changed mid-run")

    return GateResult.of(GATE_NAME, reasons)
