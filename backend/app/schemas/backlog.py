"""Backlog schemas: findings and the Scrum items they convert into.

Findings come out of read-only analysis. A finding is *evidence-backed* — it
points at the artifacts that justify it — before it can become a backlog item.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BacklogFinding(BaseModel):
    """An evidence-backed observation from read-only analysis."""

    model_config = {"extra": "forbid"}

    finding_id: str
    run_id: str
    title: str
    description: str = ""
    severity: str = "INFO"  # INFO | LOW | MEDIUM | HIGH | CRITICAL
    category: str = ""
    # Artifact paths (with hashes recorded in the evidence ledger) that back
    # this finding. A finding with no evidence cannot become a backlog item.
    evidence_artifact_paths: list[str] = Field(default_factory=list)
    recommended_action: str = ""


class BacklogItem(BaseModel):
    """A Product Backlog Item derived from a finding."""

    model_config = {"extra": "forbid"}

    item_id: str
    source_finding_id: str = ""
    title: str
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    sprint_id: str = ""
    definition_of_done_version: str = ""
    estimate: str = ""
    status: str = "DRAFT"  # DRAFT | READY | IN_SPRINT | DONE
