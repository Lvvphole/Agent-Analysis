"""Local-filesystem artifact store (Section 12.4).

MVP storage backend. Artifacts are written under the canonical path pattern::

    artifacts/{run_id}/{name}                 # run-scoped (default)
    artifacts/{run_id}/{attempt_id}/{name}    # per-attempt scoped (Epic 3)

and every write returns an :class:`Artifact` metadata record carrying the
SHA-256 hash. S3-compatible storage can later implement the same surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.schemas.artifact import Artifact
from app.storage.hashing import hash_bytes


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactStore:
    """Writes artifacts to ``{root}/{run_id}/{name}`` and hashes them.

    When an ``attempt_id`` is supplied, writes are scoped one level deeper to
    ``{root}/{run_id}/{attempt_id}/{name}`` so evidence from different attempts
    of the same run never collides (Epic 3).
    """

    def __init__(self, root: str | Path, *, attempt_id: str | None = None) -> None:
        self.root = Path(root)
        self.attempt_id = attempt_id

    def run_dir(self, run_id: str) -> Path:
        base = self.root / run_id
        return base / self.attempt_id if self.attempt_id else base

    def write(
        self,
        *,
        run_id: str,
        task_id: str,
        name: str,
        data: str | bytes,
        artifact_type: str,
        recorded_by: str = "",
    ) -> Artifact:
        """Persist ``data`` and return its hashed metadata record."""
        payload = data.encode("utf-8") if isinstance(data, str) else data
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / name
        path.write_bytes(payload)

        digest = hash_bytes(payload)
        return Artifact(
            artifact_id=f"{run_id}:{name}",
            run_id=run_id,
            task_id=task_id,
            artifact_type=artifact_type,
            path=str(path),
            hash=digest,
            created_at=_utcnow(),
            recorded_by=recorded_by,
        )

    def read_text(self, run_id: str, name: str) -> str:
        return (self.run_dir(run_id) / name).read_text(encoding="utf-8")
