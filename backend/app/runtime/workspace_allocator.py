"""Server-owned per-attempt workspace allocation (Epic 3).

Every execution of a run is an *attempt*. The server — never the caller — owns
the attempt identity and records what it ran against: a ``base_commit`` captured
from the working tree and a ``workspace_id``. Allocation introduces no authority:
it only produces audit metadata (:class:`RunAttempt`); it decides nothing and
relaxes no gate.

This is the *logical* allocation slice. The execution path is validated by the
existing :class:`WorkspacePolicy`; a fresh per-attempt checkout/copy is deferred
to the live-implementation epic (the current runtime is the read-only audit
slice, so a per-attempt repo copy would buy nothing).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.runners.git_runner import GitRunner
from app.runtime.workspace_policy import WorkspacePolicy
from app.storage.run_records import RunAttempt, RunRecord


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceAllocator:
    """Allocates the next attempt for a run against a validated workspace."""

    def __init__(self, policy: WorkspacePolicy) -> None:
        self.policy = policy

    def allocate(self, record: RunRecord, requested_path: str | Path | None) -> RunAttempt:
        """Validate the workspace and mint the next attempt for ``record``.

        Raises :class:`WorkspacePolicyError` (from the policy) on a bad path, so
        the caller can block exactly as it does today without recording an
        attempt.
        """
        resolved = self.policy.resolve(requested_path)
        attempt_number = len(record.attempts) + 1
        return RunAttempt(
            attempt_id=f"{record.run_id}-a{attempt_number}",
            attempt_number=attempt_number,
            base_commit=GitRunner(resolved).head_commit(),
            workspace_id=str(resolved),
            final_status=None,
            created_at=_utcnow(),
        )
