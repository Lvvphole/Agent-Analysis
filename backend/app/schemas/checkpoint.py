"""Checkpoint schema (Section 9.4).

Every state transition writes a checkpoint. A checkpoint records where the run
was, where it is going, and the evidence that justifies the move.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.constants import (
    CANONICAL_GITHUB_REPO_URL,
    CANONICAL_LOCAL_PROJECT_PATH,
    Decision,
)
from app.schemas.gate_result import GateResult


class Checkpoint(BaseModel):
    model_config = {"extra": "forbid"}

    run_id: str
    task_id: str = ""
    goal_id: str = ""
    sprint_id: str = ""
    product_backlog_item_id: str = ""

    state: str
    previous_state: str = ""
    next_state: str = ""

    branch: str = ""
    commit_hash: str = ""
    diff_path: str = ""
    test_output_path: str = ""
    verifier_report_path: str = ""
    evidence_ledger_path: str = ""
    evaluation_report_path: str = ""
    pr_url: str = ""

    auto_merge: bool = False
    auto_deploy: bool = False
    agent_self_certified: bool = False

    executor_id: str = ""
    coding_agent_id: str = ""
    coding_agent_run_id: str = ""
    verifier_id: str = ""
    verifier_run_id: str = ""
    verifier_decision: Decision = Decision.PENDING

    agent_attempt_count: int = 0
    verifier_failure_count: int = 0

    gate_results: list[GateResult] = Field(default_factory=list)
    next_action: str = ""

    local_project_path: str = CANONICAL_LOCAL_PROJECT_PATH
    github_repo_url: str = CANONICAL_GITHUB_REPO_URL

    created_at: str = ""
    updated_at: str = ""
