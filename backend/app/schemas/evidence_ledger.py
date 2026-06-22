"""Evidence ledger schema (Section 9.5).

The ledger is append-only. Each entry links a concrete artifact (with hash) to
a run and task. Agent narrative is never a valid ledger artifact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.constants import Decision

ArtifactType = Literal[
    "DIFF",
    "TEST",
    "LINT",
    "TYPECHECK",
    "BUILD",
    "VERIFIER_REPORT",
    "PR",
    "CHECKPOINT",
    "COMMAND_OUTPUT",
    "SCOPE_CHANGE",
    "ANALYSIS_REPORT",
    "SCRUM_MAPPING",
    "STRATEGIC_REVIEW",
    "LLM_INVOCATION",
]

LedgerResult = Literal["PASS", "FAIL", "BLOCKED", "INFO"]


class LedgerEntry(BaseModel):
    model_config = {"extra": "forbid"}

    entry_id: str
    timestamp: str = ""
    artifact_type: ArtifactType
    artifact_path: str
    command: str = ""
    result: LedgerResult = "INFO"
    # SHA-256 hex digest of the referenced artifact. Required: "Evidence
    # without hash is incomplete" (Section 9.5).
    hash: str = ""
    recorded_by: str = ""


class EvidenceLedger(BaseModel):
    model_config = {"extra": "forbid"}

    task_id: str
    run_id: str
    ledger_entries: list[LedgerEntry] = Field(default_factory=list)
    final_status: Decision = Decision.PENDING
    auto_merge: bool = False
    auto_deploy: bool = False
    agent_self_certification_used: bool = False
