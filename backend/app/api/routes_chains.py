"""Chain endpoints (handoff Section 17).

Safe surface only: introspect the registry, *plan* a chain, and *execute* a
registered chain end-to-end through the runtime spine. There is no merge,
deploy, complete, bypass, or force-pass endpoint here — and none under any
alias. Execution runs the registered, ordered chain via the ChainExecutor
(the outer authority); it never merges, deploys, or creates a PR.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.store import registry
from app.chains.registry import CHAIN_DEFINITIONS, resolve_chain
from app.constants import Decision
from app.runtime.execution_request import ChainExecuteRequest
from app.runtime.runtime_executor import build_runtime_executor, get_settings
from app.runtime.workspace_policy import WorkspacePolicyError
from app.schemas.chain import (
    ChainExecutionResult,
    ChainRequest,
    HandlerDecision,
    HandlerResult,
    HandlerStatus,
    HandlerType,
    PrStatus,
)
from app.schemas.gate_result import GateResult

router = APIRouter(tags=["chains"])


def _blocked_result(run_id: str, request: ChainRequest, reason: str) -> ChainExecutionResult:
    """A BLOCKED result that never executed the chain (e.g. bad workspace path)."""
    return ChainExecutionResult(
        run_id=request.run_id or run_id,
        task_id=request.task_id,
        task_type=request.task_type.value,
        chain_id="",
        mode=request.mode,
        handler_results=[
            HandlerResult(
                handler_name="WorkspacePolicy",
                handler_type=HandlerType.PURE_CHECK,
                status=HandlerStatus.BLOCKED,
                decision=HandlerDecision.BLOCKED,
                failure_reasons=[reason],
            )
        ],
        final_status="BLOCKED",
        verifier_decision=Decision.BLOCKED,
        pr_status=PrStatus.BLOCKED,
    )


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


@router.post("/runs/{run_id}/chain/execute")
def execute_chain(run_id: str, body: ChainExecuteRequest) -> ChainExecutionResult:
    """Execute the registered chain for a run end-to-end and store the result.

    Safe by construction: resolves only registered chains, ignores any
    request-supplied handler order (the schema forbids it), validates the real
    execution path against the workspace policy, and returns a real
    ``ChainExecutionResult``. It never merges, deploys, or creates a PR.
    """
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")

    request = body.request
    violations = request.canonical_violations()
    if violations:
        raise HTTPException(
            status_code=422, detail={"envelope_violations": violations}
        )

    settings = get_settings()
    execution_path = body.execution_path or str(settings.workspace_root)
    runtime = build_runtime_executor(settings)
    try:
        result = runtime.execute(request, execution_path=execution_path)
    except WorkspacePolicyError as exc:
        result = _blocked_result(run_id, request, f"workspace policy: {exc}")

    record.chain_execution_result = result
    record.state = "EXECUTE_CHAIN"
    return result


@router.get("/runs/{run_id}/chain/results")
def get_chain_results(run_id: str):
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    if record.chain_execution_result is not None:
        return record.chain_execution_result
    if record.chain_result is not None:
        return record.chain_result
    raise HTTPException(status_code=404, detail="no chain planned or executed for this run")
