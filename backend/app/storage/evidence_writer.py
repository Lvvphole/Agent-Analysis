"""Append-only evidence ledger writer (Section 9.5).

The writer is the only sanctioned way to grow a ledger. It generates unique,
monotonic entry ids so that the ``evidence_gate`` can detect any in-place
mutation (duplicate id) as a policy violation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.constants import Decision
from app.schemas.artifact import Artifact
from app.schemas.evidence_ledger import ArtifactType, EvidenceLedger, LedgerEntry, LedgerResult


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceLedgerWriter:
    """Builds an append-only :class:`EvidenceLedger`."""

    def __init__(self, *, task_id: str, run_id: str) -> None:
        self._ledger = EvidenceLedger(task_id=task_id, run_id=run_id)
        self._counter = 0

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    def append(
        self,
        *,
        artifact_type: ArtifactType,
        artifact_path: str,
        hash: str,
        command: str = "",
        result: LedgerResult = "INFO",
        recorded_by: str = "",
    ) -> LedgerEntry:
        """Append a hashed evidence entry and return it.

        ``hash`` is required: an unhashed entry can never support PASS, so we
        refuse to record one rather than write incomplete evidence.
        """
        if not hash:
            raise ValueError("evidence entry requires a hash")
        self._counter += 1
        entry = LedgerEntry(
            entry_id=f"E{self._counter:04d}",
            timestamp=_utcnow(),
            artifact_type=artifact_type,
            artifact_path=artifact_path,
            command=command,
            result=result,
            hash=hash,
            recorded_by=recorded_by,
        )
        self._ledger.ledger_entries.append(entry)
        return entry

    def append_artifact(
        self,
        artifact: Artifact,
        *,
        result: LedgerResult = "INFO",
        command: str = "",
    ) -> LedgerEntry:
        """Convenience: append an entry from an :class:`Artifact` record."""
        return self.append(
            artifact_type=artifact.artifact_type,  # type: ignore[arg-type]
            artifact_path=artifact.path,
            hash=artifact.hash,
            command=command,
            result=result,
            recorded_by=artifact.recorded_by,
        )

    def finalize(self, final_status: Decision) -> EvidenceLedger:
        self._ledger.final_status = final_status
        return self._ledger
