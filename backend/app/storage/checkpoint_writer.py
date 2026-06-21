"""Checkpoint writer (Section 8: "Every transition must write a checkpoint").

Serialises a :class:`Checkpoint` to the run's artifact directory and returns a
hashed :class:`Artifact` record so the checkpoint itself is evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.artifact import Artifact
from app.schemas.checkpoint import Checkpoint
from app.storage.artifact_store import ArtifactStore


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_checkpoint(
    store: ArtifactStore,
    checkpoint: Checkpoint,
    *,
    name: str = "checkpoint.json",
    recorded_by: str = "executor",
) -> Artifact:
    """Persist ``checkpoint`` and return its hashed metadata record."""
    if not checkpoint.created_at:
        checkpoint = checkpoint.model_copy(update={"created_at": _utcnow()})
    checkpoint = checkpoint.model_copy(update={"updated_at": _utcnow()})
    return store.write(
        run_id=checkpoint.run_id,
        task_id=checkpoint.task_id,
        name=name,
        data=checkpoint.model_dump_json(indent=2),
        artifact_type="CHECKPOINT",
        recorded_by=recorded_by,
    )
