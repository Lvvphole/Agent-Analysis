"""Scrum mapping schema (Section 9.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScrumMapping(BaseModel):
    """Maps an autonomous task onto Scrum artifacts.

    A task cannot enter execution unless every required field here is present
    and acceptance criteria are testable (enforced by ``scrum_gate``).
    """

    model_config = {"extra": "forbid"}

    product_backlog_item_id: str = ""
    product_backlog_item_title: str = ""
    sprint_id: str = ""
    sprint_goal: str = ""
    sprint_backlog_task_id: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    definition_of_done_version: str = ""
    increment_candidate: bool = False
    # Optional, explicit linkage that the task supports the sprint goal.
    supports_sprint_goal: bool = True
