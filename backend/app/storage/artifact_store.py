"""Local-filesystem artifact store (Section 12.4).

MVP storage backend. Artifacts are written under the canonical path pattern::

    artifacts/{run_id}/{name}

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
    """Writes artifacts to ``{root}/{run_id}/{name}`` and hashes them."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

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
