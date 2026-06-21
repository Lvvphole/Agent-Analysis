"""State machines and transition guards (Sections 7 and 8).

No state advances by narrative. A transition is admissible only when the
artifacts required to leave the current state are present. Field-level policy
(manifest, scrum, evidence, ...) lives in the dedicated gates; this module owns
*ordering* and *artifact presence* so those responsibilities stay separated.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.constants import (
    ANALYSIS_STATE_ORDER,
    IMPLEMENTATION_STATE_ORDER,
    RunType,
)
from app.schemas.gate_result import GateResult

GATE_NAME = "state_transition_guard"

# Terminal state shared by both machines.
TERMINAL_STATE = "STOP_OR_LOOP"

# Artifacts required to *leave* each state (Section 8 for IMPLEMENTATION; the
# READ_ONLY_ANALYSIS machine mirrors the same shape with analysis evidence).
_IMPLEMENTATION_REQUIRED: dict[str, tuple[str, ...]] = {
    "INTAKE": ("task_contract.json", "run_manifest.json"),
    "REFINE": ("scrum_mapping.json", "acceptance_criteria.json", "complexity_risk.json"),
    "PLAN": (
        "task_plan.json",
        "command_plan.json",
        "scope_plan.json",
        "rollback_plan.json",
        "definition_of_done_lock.json",
    ),
    "DESIGN_GATE": (
        "design_options.json",
        "selected_design.json",
        "strategic_programming_contract.json",
    ),
    "AGENT_INVOKE": (
        "agent_invocation.md",
        "agent_summary.md",
        "raw_agent_output.log",
        "file_change_record.json",
    ),
    "DIFF_CAPTURE": ("diff.patch", "git_status.log", "diff_check.log"),
    "TEST": ("test_output.log",),
    "VERIFY": ("verifier_report.json", "evidence_ledger.json"),
    "EVALUATE": ("evaluation_report.json",),
    "MEMORY_UPDATE": ("memory_update_record.json",),  # or skip-reason, see below
    "PR_GATE": ("pr_gate_report.json", "final_checkpoint.json"),
}

# MEMORY_UPDATE may instead present an explicit skip reason (Section 8.10).
_ALTERNATIVE_REQUIRED: dict[str, tuple[tuple[str, ...], ...]] = {
    "MEMORY_UPDATE": (
        ("memory_update_record.json",),
        ("memory_update_skip_reason.json",),
    ),
}

_ANALYSIS_REQUIRED: dict[str, tuple[str, ...]] = {
    "INTAKE": ("task_contract.json", "run_manifest.json"),
    "REFINE": ("scrum_mapping.json", "acceptance_criteria.json", "complexity_risk.json"),
    "PLAN": (
        "task_plan.json",
        "command_plan.json",
        "scope_plan.json",
        "rollback_plan.json",
        "definition_of_done_lock.json",
    ),
    "DESIGN_GATE": (
        "design_options.json",
        "selected_design.json",
        "strategic_programming_contract.json",
    ),
    "AGENT_INVOKE_READONLY": ("repo_tree.log", "command_discovery.log"),
    "EVIDENCE_CAPTURE": ("codebase_ai_readiness_report.json", "evidence_ledger.json"),
    "VERIFY_ANALYSIS": ("verifier_report.json",),
    "EVALUATE": ("evaluation_report.json",),
    "BACKLOG_UPDATE": ("ai_safety_gap_backlog.json", "final_checkpoint.json"),
}


def _order(run_type: RunType) -> tuple[str, ...]:
    if run_type == RunType.IMPLEMENTATION:
        return IMPLEMENTATION_STATE_ORDER
    return ANALYSIS_STATE_ORDER


def _required(run_type: RunType) -> dict[str, tuple[str, ...]]:
    return (
        _IMPLEMENTATION_REQUIRED
        if run_type == RunType.IMPLEMENTATION
        else _ANALYSIS_REQUIRED
    )


def next_state(run_type: RunType, current_state: str) -> str | None:
    """Return the next state in order, or ``None`` at the terminal state."""
    order = _order(run_type)
    if current_state not in order:
        raise ValueError(f"unknown state {current_state!r} for {run_type}")
    idx = order.index(current_state)
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


def diff_required(run_type: RunType) -> bool:
    """Implementation mode requires a diff; read-only analysis never does."""
    return run_type == RunType.IMPLEMENTATION


def transition_guard(
    run_type: RunType,
    current_state: str,
    present_artifacts: Iterable[str],
) -> GateResult:
    """Return PASS only if the artifacts required to leave ``current_state`` exist.

    ``present_artifacts`` is matched by basename so callers may pass full paths.
    """
    order = _order(run_type)
    if current_state not in order:
        return GateResult.of(
            GATE_NAME, [f"unknown state {current_state!r} for {run_type.value}"]
        )

    present = {p.replace("\\", "/").rsplit("/", 1)[-1] for p in present_artifacts}

    # Alternative requirement sets (any one set satisfies the transition).
    alternatives = _ALTERNATIVE_REQUIRED.get(current_state)
    if alternatives is not None:
        if any(all(name in present for name in option) for option in alternatives):
            return GateResult.of(GATE_NAME, [])
        wanted = " or ".join("/".join(opt) for opt in alternatives)
        return GateResult.of(
            GATE_NAME, [f"missing required artifacts to leave {current_state}: {wanted}"]
        )

    required = _required(run_type).get(current_state, ())
    missing = [name for name in required if name not in present]
    reasons = [
        f"missing required artifact to leave {current_state}: {name}"
        for name in missing
    ]
    return GateResult.of(GATE_NAME, reasons)
