"""The in-flight run record.

A ``RunRecord`` is the state-of-the-world snapshot the control API keeps for one
run. It is deliberately *not* the source of truth for PASS — only a verifier
report decides that. It is the unit a :class:`RunRepository` persists and
retrieves; moving it here (out of the API layer) lets both the in-memory and the
Postgres adapters depend on it without importing the routers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.chain import ChainExecutionResult
from app.schemas.run_manifest import RunManifest
from app.schemas.verifier_report import VerifierReport


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
