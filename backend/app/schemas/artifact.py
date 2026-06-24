"""Artifact metadata schema (Section 12.4).

Large artifact *content* lives in artifact storage; this model is the metadata
record (path, hash, linkage) that the database and evidence ledger reference.
"""

from __future__ import annotations

from pydantic import BaseModel


class Artifact(BaseModel):
    model_config = {"extra": "forbid"}

    artifact_id: str
    run_id: str
    task_id: str
    artifact_type: str
    path: str
    # SHA-256 hex digest. Every artifact must be hashed (Section 12.4).
    hash: str
    # The attempt that produced this artifact (Epic 3 per-attempt scoping). None
    # for run-scoped writes that did not run under an attempt.
    attempt_id: str | None = None
    created_at: str = ""
    recorded_by: str = ""
