"""Chain endpoints (handoff Section 17).

Safe surface only: introspect the registry and validate/plan a chain for a run.
There is no merge, deploy, complete, bypass, or force-pass endpoint here — and
none under any alias. Actually running a chain against a working tree is
deferred (it needs the deferred runners + a real checkout); this endpoint
validates the envelope and resolves the registered, ordered plan.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.store import registry
from app.chains.registry import CHAIN_DEFINITIONS, resolve_chain
from app.schemas.chain import ChainRequest
from app.schemas.gate_result import GateResult

router = APIRouter(tags=["chains"])


def _definition_dict(chain_id: str) -> dict:
    d = CHAIN_DEFINITIONS[chain_id]
    return {
        "chain_id": d.chain_id,
        "mode": d.mode.value,
        "handler_names": list(d.handler_names),
    }


@router.get("/chains")
def list_chains() -> list[dict]:
    return [_definition_dict(cid) for cid in CHAIN_DEFINITIONS]


@router.get("/chains/{chain_id}")
def get_chain(chain_id: str) -> dict:
    if chain_id not in CHAIN_DEFINITIONS:
        raise HTTPException(status_code=404, detail="chain not found")
    return _definition_dict(chain_id)


@router.post("/runs/{run_id}/chain")
def plan_chain(run_id: str, request: ChainRequest) -> dict:
    """Validate the envelope and resolve the registered chain plan for a run.

    Unknown task types are BLOCKED (no chain). An agent cannot reorder the plan;
    it is returned verbatim from the registry.
    """
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")

    envelope = GateResult.of("chain_envelope", request.canonical_violations())
    chain = resolve_chain(request.task_type.value)
    if chain is None:
        result = {
            "run_id": run_id,
            "task_type": request.task_type.value,
            "final_status": "BLOCKED",
            "reason": "unknown task_type has no registered chain",
            "envelope_gate": envelope.model_dump(),
        }
        record.chain_result = result
        return result

    result = {
        "run_id": run_id,
        "task_type": request.task_type.value,
        "chain_id": chain.chain_id,
        "mode": chain.mode.value,
        "handler_names": list(chain.handler_names),
        "envelope_gate": envelope.model_dump(),
        "execution": "deferred: chain execution requires runners + a checkout",
        "auto_merge": False,
        "auto_deploy": False,
    }
    record.chain_result = result
    return result


@router.get("/runs/{run_id}/chain/results")
def get_chain_results(run_id: str) -> dict:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    if record.chain_result is None:
        raise HTTPException(status_code=404, detail="no chain planned for this run")
    return record.chain_result
