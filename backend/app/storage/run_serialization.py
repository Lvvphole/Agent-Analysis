"""JSON (de)serialization for :class:`RunRecord`.

The durable ``runs.snapshot`` column stores the whole record as JSON so a run can
be reconstructed exactly across a process restart. Keeping the codec here (not
inside the Postgres adapter) means it can be unit-tested with no database.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.schemas.artifact import Artifact
from app.schemas.chain import ChainExecutionResult
from app.schemas.run_manifest import RunManifest
from app.schemas.verifier_report import VerifierReport
from app.storage.run_records import RunAttempt, RunRecord


def record_to_snapshot(record: RunRecord) -> dict[str, Any]:
    """Serialize a record to a JSON-safe dict (the authoritative snapshot)."""
    return {
        "run_id": record.run_id,
        "state": record.state,
        "tenant_id": record.tenant_id,
        "manifest": record.manifest.model_dump(mode="json"),
        "verifier_report": (
            record.verifier_report.model_dump(mode="json")
            if record.verifier_report is not None
            else None
        ),
        "chain_result": record.chain_result,
        "chain_execution_result": (
            record.chain_execution_result.model_dump(mode="json")
            if record.chain_execution_result is not None
            else None
        ),
        "llm_invocations": list(record.llm_invocations),
        "attempts": [asdict(attempt) for attempt in record.attempts],
        "artifacts": [a.model_dump(mode="json") for a in record.artifacts],
    }


def record_from_snapshot(snapshot: dict[str, Any]) -> RunRecord:
    """Reconstruct a record from a snapshot produced by :func:`record_to_snapshot`."""
    verifier_report = snapshot.get("verifier_report")
    chain_execution_result = snapshot.get("chain_execution_result")
    return RunRecord(
        run_id=snapshot["run_id"],
        manifest=RunManifest(**snapshot["manifest"]),
        state=snapshot.get("state", "INTAKE"),
        verifier_report=(
            VerifierReport(**verifier_report) if verifier_report is not None else None
        ),
        chain_result=snapshot.get("chain_result"),
        chain_execution_result=(
            ChainExecutionResult(**chain_execution_result)
            if chain_execution_result is not None
            else None
        ),
        llm_invocations=list(snapshot.get("llm_invocations") or []),
        tenant_id=snapshot.get("tenant_id"),
        attempts=[RunAttempt(**a) for a in snapshot.get("attempts") or []],
        artifacts=[Artifact(**a) for a in snapshot.get("artifacts") or []],
    )
