"""The in-flight run record.

A ``RunRecord`` is the state-of-the-world snapshot the control API keeps for one
run. It is deliberately *not* the source of truth for PASS — only a verifier
report decides that. It is the unit a :class:`RunRepository` persists and
retrieves; moving it here (out of the API layer) lets both the in-memory and the
Postgres adapters depend on it without importing the routers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.artifact import Artifact
from app.schemas.chain import ChainExecutionResult
from app.schemas.run_manifest import RunManifest
from app.schemas.verifier_report import VerifierReport


@dataclass
class RunAttempt:
    """One server-owned execution attempt of a run (Epic 3).

    Mirrors the ``run_attempts`` durable table. The server allocates the
    identity (``attempt_id``/``attempt_number``) and records what it ran against
    (``base_commit``, ``workspace_id``) — it is audit metadata only and decides
    nothing. ``final_status`` echoes the attempt's chain result; PASS authority
    still rests solely with the verifier.
    """

    attempt_id: str
    attempt_number: int
    base_commit: str | None = None
    workspace_id: str | None = None
    final_status: str | None = None
    created_at: str | None = None


@dataclass
class RunRecord:
    run_id: str
    manifest: RunManifest
    state: str = "INTAKE"
    verifier_report: VerifierReport | None = None
    chain_result: dict | None = None
    chain_execution_result: ChainExecutionResult | None = None
    llm_invocations: list = field(default_factory=list)
    # Reserved for Epic 5 (multi-user access control). Persisted now so the
    # durable schema does not need a migration to become tenant-aware later.
    tenant_id: str | None = None
    # Per-attempt isolation (Epic 3). Embedded in the record so it round-trips
    # through the snapshot and needs no new RunRepository port method.
    attempts: list[RunAttempt] = field(default_factory=list)
    # Hashed evidence artifacts produced across the run's attempts (Epic 6).
    # Embedded like attempts; projected into evidence_artifacts. Never returned
    # by the API — Artifact.path is an internal host path.
    artifacts: list[Artifact] = field(default_factory=list)
