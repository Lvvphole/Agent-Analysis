"""In-memory run registry for the MVP control API.

This is deliberately simple state-of-the-world storage. It is *not* the source
of truth for PASS — only verifier reports decide that. PostgreSQL replaces this
in a later phase; the surface is intentionally small so that swap is contained.
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


@dataclass
class RunRegistry:
    runs: dict[str, RunRecord] = field(default_factory=dict)

    def add(self, record: RunRecord) -> None:
        self.runs[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        return self.runs.get(run_id)

    def list(self) -> list[RunRecord]:
        return list(self.runs.values())


# Module-level singleton used by the routers for the MVP.
registry = RunRegistry()
