"""State machine and transition guard tests (Sections 7, 8, 19)."""

from __future__ import annotations

from app.constants import GateStatus, RunType
from app.state_machine import (
    diff_required,
    next_state,
    transition_guard,
)


def test_implementation_order_is_canonical():
    assert next_state(RunType.IMPLEMENTATION, "INTAKE") == "REFINE"
    assert next_state(RunType.IMPLEMENTATION, "DIFF_CAPTURE") == "TEST"
    assert next_state(RunType.IMPLEMENTATION, "STOP_OR_LOOP") is None


def test_analysis_order_is_canonical():
    assert next_state(RunType.READ_ONLY_ANALYSIS, "DESIGN_GATE") == "AGENT_INVOKE_READONLY"
    assert next_state(RunType.READ_ONLY_ANALYSIS, "VERIFY_ANALYSIS") == "EVALUATE"


def test_intake_guard_requires_artifacts():
    fail = transition_guard(RunType.IMPLEMENTATION, "INTAKE", [])
    assert fail.status == GateStatus.FAIL

    ok = transition_guard(
        RunType.IMPLEMENTATION,
        "INTAKE",
        ["artifacts/run-1/task_contract.json", "run_manifest.json"],
    )
    assert ok.status == GateStatus.PASS


def test_diff_capture_guard_requires_diff():
    fail = transition_guard(
        RunType.IMPLEMENTATION, "DIFF_CAPTURE", ["git_status.log", "diff_check.log"]
    )
    assert fail.status == GateStatus.FAIL
    assert any("diff.patch" in r for r in fail.reasons)


def test_memory_update_alternative_skip_reason_passes():
    ok = transition_guard(
        RunType.IMPLEMENTATION, "MEMORY_UPDATE", ["memory_update_skip_reason.json"]
    )
    assert ok.status == GateStatus.PASS


def test_implementation_requires_diff_readonly_does_not():
    assert diff_required(RunType.IMPLEMENTATION) is True
    assert diff_required(RunType.READ_ONLY_ANALYSIS) is False


def test_readonly_no_diff_capture_state_exists():
    # The read-only machine never has a DIFF_CAPTURE state requiring diff.patch.
    fail = transition_guard(
        RunType.READ_ONLY_ANALYSIS,
        "AGENT_INVOKE_READONLY",
        ["repo_tree.log", "command_discovery.log"],
    )
    assert fail.status == GateStatus.PASS
