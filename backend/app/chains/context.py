"""Shared execution context for a chain run.

The context carries services (artifact store, evidence writer) and accumulates
state across handlers. Its ``record_artifact`` helper is the single sanctioned
path for a handler to create evidence: it writes through the artifact store
(which hashes) and appends to the append-only evidence ledger. Hashing and
evidence therefore cannot be skipped or faked by a handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.constants import Decision
from app.gates.test_gate import TestOutcome
from app.schemas.artifact import Artifact
from app.schemas.backlog import BacklogFinding
from app.schemas.chain import ChainRequest
from app.schemas.evidence_ledger import ArtifactType, LedgerResult
from app.schemas.run_manifest import RunManifest
from app.schemas.scrum_mapping import ScrumMapping
from app.schemas.strategic_programming import StrategicProgramming
from app.storage.artifact_store import ArtifactStore
from app.storage.evidence_writer import EvidenceLedgerWriter
from app.storage.hashing import hash_file


def snapshot_repo(repo_path: Path) -> dict[str, str]:
    """Map of relative path -> sha256 for every file under ``repo_path``.

    Used to prove read-only modes never mutate the repository.
    """
    snapshot: dict[str, str] = {}
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules"}
    for path in repo_path.rglob("*"):
        rel = path.relative_to(repo_path)
        if any(part in skip for part in rel.parts):
            continue
        if path.is_file():
            snapshot[str(rel)] = hash_file(path)
    return snapshot


@dataclass
class ChainContext:
    request: ChainRequest
    store: ArtifactStore
    evidence: EvidenceLedgerWriter
    repo_fs_path: Path
    manifest: RunManifest | None = None
    scrum: ScrumMapping | None = None
    strategic: StrategicProgramming | None = None

    locked_dod_version: str | None = None
    repo_snapshot: dict[str, str] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    test_outcomes: list[TestOutcome] = field(default_factory=list)

    coding_agent_run_id: str = ""
    verifier_run_id: str = ""
    verifier_decision: Decision = Decision.PENDING
    agent_summary_quarantined: bool = False
    agent_self_certification_used: bool = False

    eval_score: float | None = None
    readiness_report: dict = field(default_factory=dict)
    findings: list[BacklogFinding] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    shared: dict = field(default_factory=dict)

    # Optional runtime services threaded in by the RuntimeExecutor. When absent
    # the agent/tool steps SKIP and the deterministic chain remains the proof.
    # Typed loosely to avoid import cycles (agents/tools import schemas/context).
    agent_specs: list = field(default_factory=list)
    agent_adapters: dict = field(default_factory=dict)
    tool_registry: object | None = None
    tool_policy: object | None = None

    @property
    def run_id(self) -> str:
        return self.request.run_id

    @property
    def task_id(self) -> str:
        return self.request.task_id

    def record_artifact(
        self,
        *,
        name: str,
        data: str,
        artifact_type: ArtifactType,
        result: LedgerResult = "INFO",
        command: str = "",
        recorded_by: str = "",
    ) -> Artifact:
        """Write a hashed artifact and append it to the evidence ledger."""
        artifact = self.store.write(
            run_id=self.run_id,
            task_id=self.task_id,
            name=name,
            data=data,
            artifact_type=artifact_type,
            recorded_by=recorded_by,
        )
        self.evidence.append_artifact(artifact, result=result, command=command)
        self.artifacts.append(artifact)
        return artifact

    def write_quarantined(self, *, name: str, data: str, recorded_by: str = "") -> Artifact:
        """Write agent output to the store WITHOUT adding it to the evidence
        ledger. Agent narrative is context only (Section 6.2 quarantine rule):
        it is never evidence, so it must never enter the ledger."""
        return self.store.write(
            run_id=self.run_id,
            task_id=self.task_id,
            name=name,
            data=data,
            artifact_type="COMMAND_OUTPUT",
            recorded_by=recorded_by,
        )
