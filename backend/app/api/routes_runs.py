"""Run lifecycle endpoints (Section 11).

Implements only the *safe* surface. The forbidden endpoints
(``/complete``, ``/merge``, ``/deploy``, ``/bypass``, ``/force-pass``) are
intentionally absent — completion comes from a verifier report, and merge /
deploy live outside this autonomous loop.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.constants import Decision
from app.gates.evidence_gate import evidence_gate
from app.gates.manifest_gate import manifest_gate
from app.gates.no_self_certification_gate import no_self_certification_gate
from app.gates.pr_gate import pr_gate
from app.api.store import RunRecord, registry
from app.schemas.evidence_ledger import EvidenceLedger
from app.schemas.gate_result import GateResult
from app.schemas.run_manifest import RunManifest
from app.schemas.verifier_report import VerifierReport

router = APIRouter(prefix="/runs", tags=["runs"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CreateRunResponse(BaseModel):
    run_id: str
    state: str
    manifest_gate: GateResult


@router.post("", response_model=CreateRunResponse, status_code=201)
def create_run(manifest: RunManifest) -> CreateRunResponse:
    """Validate a manifest through the manifest gate and register the run.

    A run is never created on an inadmissible manifest.
    """
    gate = manifest_gate(manifest)
    if not gate.passed:
        raise HTTPException(status_code=422, detail=gate.model_dump())

    run_id = manifest.run_id or f"run-{uuid.uuid4().hex[:12]}"
    record = RunRecord(run_id=run_id, manifest=manifest, state="INTAKE")
    registry.add(record)
    return CreateRunResponse(run_id=run_id, state=record.state, manifest_gate=gate)


@router.get("")
def list_runs() -> list[dict]:
    return [{"run_id": r.run_id, "state": r.state} for r in registry.list()]


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": record.run_id,
        "state": record.state,
        "manifest": record.manifest.model_dump(),
        "verifier_decision": (
            record.verifier_report.decision if record.verifier_report else Decision.PENDING
        ),
    }


@router.get("/{run_id}/state")
def get_run_state(run_id: str) -> dict:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": record.run_id, "state": record.state}


class VerifyRequest(BaseModel):
    verifier_report: VerifierReport
    evidence_ledger: EvidenceLedger


@router.post("/{run_id}/verify")
def verify_run(run_id: str, body: VerifyRequest) -> dict:
    """Record an independent verifier decision.

    Re-runs the no-self-certification and evidence gates server-side: the API
    will not let a self-certified or unhashed-evidence report stand as PASS.
    """
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")

    report = body.verifier_report
    ledger = body.evidence_ledger

    self_cert = no_self_certification_gate(
        coding_agent_run_id=report.coding_agent_run_id,
        verifier_run_id=report.verifier_run_id,
        verifier_decision=report.decision,
        agent_summary_used_as_evidence=ledger.agent_self_certification_used,
    )
    ev = evidence_gate(
        ledger,
        run_id=record.run_id,
        task_id=report.task_id,
    )

    # A reported PASS is only honoured when the independent gates also pass.
    effective = report.decision
    blocking = [g for g in (self_cert, ev) if not g.passed]
    if report.decision == Decision.PASS and blocking:
        effective = Decision.FAIL

    record.verifier_report = report.model_copy(update={"decision": effective})
    record.state = "VERIFY"
    return {
        "run_id": record.run_id,
        "reported_decision": report.decision,
        "effective_decision": effective,
        "no_self_certification_gate": self_cert.model_dump(),
        "evidence_gate": ev.model_dump(),
    }


class PrRequest(BaseModel):
    pr_url: str = ""
    pr_skip_reason: str = ""


@router.post("/{run_id}/pr")
def create_or_update_pr(run_id: str, body: PrRequest) -> dict:
    """Allow a gated PR only after an independent verifier PASS.

    There is no merge and no deploy here. The PR gate re-asserts that.
    """
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    decision = record.verifier_report.decision if record.verifier_report else Decision.PENDING
    if decision != Decision.PASS:
        raise HTTPException(
            status_code=409, detail="verifier PASS required before PR creation"
        )

    gate = pr_gate(
        verifier_decision=decision,
        pr_url=body.pr_url,
        pr_skip_reason=body.pr_skip_reason,
        auto_merge=record.manifest.auto_merge,
        auto_deploy=record.manifest.auto_deploy,
    )
    if not gate.passed:
        raise HTTPException(status_code=422, detail=gate.model_dump())

    record.state = "PR_GATE"
    return {
        "run_id": record.run_id,
        "pr_url": body.pr_url,
        "pr_gate": gate.model_dump(),
        "auto_merge": False,
        "auto_deploy": False,
        "human_approval_required": True,
    }
