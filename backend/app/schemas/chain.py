"""Chain of Responsibility schemas (handoff Sections 6, 7, 8, 12).

These typed contracts make the forbidden states unrepresentable:
- ``HandlerDecision`` has no DONE/MERGE/DEPLOY/FORCE_PASS/AUTO_PASS member, so a
  handler literally cannot return one.
- ``handler_type`` and ``status`` are required, so a malformed result is
  rejected at construction.

The harness (executor) — not the handler — decides PASS from a VERIFIER handler
plus the existing gates. These schemas only describe shape.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.constants import (
    CANONICAL_GITHUB_REPO_URL,
    CANONICAL_LOCAL_PROJECT_PATH,
    Decision,
    RunType,
)
from app.schemas.artifact import Artifact
from app.schemas.gate_result import GateResult


class TaskType(str, Enum):
    AI_READINESS_AUDIT = "AI_READINESS_AUDIT"
    IMPLEMENTATION = "IMPLEMENTATION"
    BUG_FIX = "BUG_FIX"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    DEPENDENCY_UPDATE = "DEPENDENCY_UPDATE"
    DOCUMENTATION_UPDATE = "DOCUMENTATION_UPDATE"
    CI_FAILURE_REPAIR = "CI_FAILURE_REPAIR"
    REFACTOR = "REFACTOR"
    TEST_COVERAGE_EXPANSION = "TEST_COVERAGE_EXPANSION"


class HandlerType(str, Enum):
    PURE_CHECK = "PURE_CHECK"
    READ_ONLY_COMMAND = "READ_ONLY_COMMAND"
    WRITE_COMMAND = "WRITE_COMMAND"
    AGENT_INVOCATION = "AGENT_INVOCATION"
    VERIFIER = "VERIFIER"
    PR_ACTION = "PR_ACTION"
    EVALUATOR = "EVALUATOR"


class HandlerStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class HandlerDecision(str, Enum):
    # Deliberately excludes DONE / MERGE / DEPLOY / FORCE_PASS / AUTO_PASS.
    CONTINUE = "CONTINUE"
    SKIP_NOT_APPLICABLE = "SKIP_NOT_APPLICABLE"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    STOP = "STOP"


class PrStatus(str, Enum):
    GATED = "GATED"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"


# Handler types permitted to modify the repository (only inside scope).
REPO_WRITE_TYPES = frozenset({HandlerType.WRITE_COMMAND, HandlerType.AGENT_INVOCATION})


class ScrumEnvelope(BaseModel):
    model_config = {"extra": "forbid"}

    product_backlog_item_id: str = ""
    sprint_goal: str = ""
    sprint_backlog_task_id: str = ""
    definition_of_done_version: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)


class ScopeEnvelope(BaseModel):
    model_config = {"extra": "forbid"}

    files_in_scope: list[str] = Field(default_factory=list)
    files_out_of_scope: list[str] = Field(default_factory=list)


class HardRules(BaseModel):
    model_config = {"extra": "forbid"}

    auto_merge: bool = False
    auto_deploy: bool = False
    parallel_tool_calls: bool = False
    agent_self_certification_allowed: bool = False


class ChainRequest(BaseModel):
    """Routing envelope (Section 6). ``repo_path`` is the canonical *identity*
    string validated against the constant; the real filesystem path used for
    I/O is passed separately to the executor."""

    model_config = {"extra": "forbid"}

    run_id: str = ""
    task_id: str = ""
    task_type: TaskType
    mode: RunType
    state: str = ""
    repo_path: str = CANONICAL_LOCAL_PROJECT_PATH
    github_repo_url: str = CANONICAL_GITHUB_REPO_URL
    scrum: ScrumEnvelope = Field(default_factory=ScrumEnvelope)
    scope: ScopeEnvelope = Field(default_factory=ScopeEnvelope)
    hard_rules: HardRules = Field(default_factory=HardRules)
    artifacts: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def canonical_violations(self) -> list[str]:
        """Hard envelope validation (Section 6). Empty list => admissible."""
        reasons: list[str] = []
        if self.repo_path != CANONICAL_LOCAL_PROJECT_PATH:
            reasons.append("repo_path must equal " + CANONICAL_LOCAL_PROJECT_PATH)
        if self.github_repo_url != CANONICAL_GITHUB_REPO_URL:
            reasons.append("github_repo_url must equal " + CANONICAL_GITHUB_REPO_URL)
        if self.hard_rules.auto_merge:
            reasons.append("auto_merge must be false")
        if self.hard_rules.auto_deploy:
            reasons.append("auto_deploy must be false")
        if self.hard_rules.parallel_tool_calls:
            reasons.append("parallel_tool_calls must be false")
        if self.hard_rules.agent_self_certification_allowed:
            reasons.append("agent_self_certification_allowed must be false")
        return reasons


class HandlerResult(BaseModel):
    """Structured result every handler must return (Section 7)."""

    model_config = {"extra": "forbid"}

    handler_name: str
    handler_type: HandlerType
    status: HandlerStatus
    decision: HandlerDecision
    artifacts_created: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)
    next_handler: str = ""
    failure_reasons: list[str] = Field(default_factory=list)
    required_corrections: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ChainExecutionResult(BaseModel):
    """Final, harness-owned result of a chain run (Section 12)."""

    model_config = {"extra": "forbid"}

    run_id: str
    task_id: str
    task_type: str
    chain_id: str
    mode: RunType
    handler_results: list[HandlerResult] = Field(default_factory=list)
    final_status: Literal["PASS", "FAIL", "BLOCKED"] = "BLOCKED"
    verifier_decision: Decision = Decision.PENDING
    eval_score: float | None = None
    pr_status: PrStatus = PrStatus.NOT_REQUIRED
    agent_self_certification_used: bool = False
    auto_merge: bool = False
    auto_deploy: bool = False
    # In-process carrier for the hashed evidence artifacts produced during the
    # run, so the API layer can persist/project them into evidence_artifacts.
    # exclude=True keeps it out of every API response — Artifact.path is an
    # absolute host path and must never be exposed (cf. the workspace_id leak).
    evidence_artifacts: list[Artifact] = Field(default_factory=list, exclude=True)
