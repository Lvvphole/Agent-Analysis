"""Scrum gate tests (Sections 13.2, 19)."""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.scrum_gate import scrum_gate

from tests.conftest import make_scrum


def test_valid_scrum_mapping_passes():
    assert scrum_gate(make_scrum()).status == GateStatus.PASS


def test_missing_pbi_fails():
    result = scrum_gate(make_scrum(product_backlog_item_id=""))
    assert "Product Backlog Item missing" in result.reasons


def test_missing_sprint_goal_fails():
    result = scrum_gate(make_scrum(sprint_goal=""))
    assert "Sprint Goal missing" in result.reasons


def test_missing_sprint_backlog_task_fails():
    result = scrum_gate(make_scrum(sprint_backlog_task_id=""))
    assert "Sprint Backlog task missing" in result.reasons


def test_missing_acceptance_criteria_blocks_execution():
    result = scrum_gate(make_scrum(acceptance_criteria=[]))
    assert result.status == GateStatus.FAIL
    assert "acceptance criteria missing" in result.reasons


def test_untestable_acceptance_criteria_fails():
    result = scrum_gate(make_scrum(acceptance_criteria=["nice", "ok"]))
    assert "acceptance criteria not testable" in result.reasons


def test_missing_dod_version_fails():
    result = scrum_gate(make_scrum(definition_of_done_version=""))
    assert "Definition of Done version missing" in result.reasons


def test_task_not_supporting_sprint_goal_fails():
    result = scrum_gate(make_scrum(supports_sprint_goal=False))
    assert "task does not support Sprint Goal" in result.reasons


def test_definition_of_done_mutation_blocks_pass():
    # Locked at dod-v1 during PLAN, mapping now claims dod-v2 to force a pass.
    result = scrum_gate(
        make_scrum(definition_of_done_version="dod-v2"),
        locked_definition_of_done_version="dod-v1",
    )
    assert result.status == GateStatus.FAIL
    assert "Definition of Done changed mid-run" in result.reasons
