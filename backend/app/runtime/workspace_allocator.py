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

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.runners.git_runner import GitRunner
from app.runtime.workspace_policy import WorkspacePolicy
from app.storage.run_records import RunAttempt, RunRecord


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkspaceAllocation:
    """The result of allocating an attempt: public identity + internal path.

    ``attempt`` is the audit record that is persisted and returned by the API; its
    ``workspace_id`` is an **opaque** identifier, never a filesystem path.
    ``execution_path`` is the validated, resolved host path the chain actually runs
    against — it stays in-process and is *never* persisted or exposed by the API.
    Keeping the two apart is what stops the audit surface from leaking host layout.
    """

    attempt: RunAttempt
    execution_path: Path


class WorkspaceAllocator:
    """Allocates the next attempt for a run against a validated workspace."""

    def __init__(self, policy: WorkspacePolicy) -> None:
        self.policy = policy

    def allocate(
        self, record: RunRecord, requested_path: str | Path | None
    ) -> WorkspaceAllocation:
        """Validate the workspace and mint the next attempt for ``record``.

        Raises :class:`WorkspacePolicyError` (from the policy) on a bad path, so
        the caller can block exactly as it does today without recording an
        attempt. The returned attempt carries only an opaque ``workspace_id``; the
        resolved host path travels separately on the allocation's
        ``execution_path``.
        """
        resolved = self.policy.resolve(requested_path)
        attempt_number = len(record.attempts) + 1
        attempt = RunAttempt(
            attempt_id=f"{record.run_id}-a{attempt_number}",
            attempt_number=attempt_number,
            base_commit=GitRunner(resolved).head_commit(),
            workspace_id=f"workspace-{record.run_id}-a{attempt_number}",
            final_status=None,
            created_at=_utcnow(),
        )
        return WorkspaceAllocation(attempt=attempt, execution_path=resolved)
