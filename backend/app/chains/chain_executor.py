"""Chain executor — the harness loop (handoff Section 4, 12).

The executor is the outer authority. It resolves the registered chain, runs
handlers in registered order ONLY, routes every artifact through hashing +
evidence + checkpoint, enforces the authority matrix, and decides the final
status. A handler result alone never advances or finalizes state.
"""

from __future__ import annotations

from pathlib import Path

from app.chains.context import ChainContext, snapshot_repo
from app.chains.registry import resolve_chain
from app.constants import Decision, RunType
from app.handlers.authority import can_decide_pass, can_modify_repo
from app.handlers.base import HandlerRegistry, build_default_registry
from app.schemas.chain import (
    ChainExecutionResult,
    ChainRequest,
    HandlerDecision,
    HandlerResult,
    HandlerStatus,
    HandlerType,
    PrStatus,
)
from app.schemas.checkpoint import Checkpoint
from app.schemas.run_manifest import RunManifest
from app.schemas.scrum_mapping import ScrumMapping
from app.storage.artifact_store import ArtifactStore
from app.storage.checkpoint_writer import write_checkpoint
from app.storage.evidence_writer import EvidenceLedgerWriter

_STATUS_TO_DECISION = {
    HandlerStatus.PASS: Decision.PASS,
    HandlerStatus.FAIL: Decision.FAIL,
    HandlerStatus.BLOCKED: Decision.BLOCKED,
}


class ChainExecutor:
    def __init__(self, handler_registry: HandlerRegistry | None = None) -> None:
        self.registry = handler_registry or build_default_registry()

    def execute(
        self,
        request: ChainRequest,
        *,
        store: ArtifactStore,
        repo_fs_path: str | Path,
        manifest: RunManifest | None = None,
        scrum: ScrumMapping | None = None,
        agent_specs: list | None = None,
        agent_adapters: dict | None = None,
        tool_registry: object | None = None,
        tool_policy: object | None = None,
    ) -> ChainExecutionResult:
        chain = resolve_chain(request.task_type.value)
        if chain is None:
            return self._blocked_result(
                request, chain_id="", reasons=[f"unknown task_type: {request.task_type.value}"]
            )

        repo_fs_path = Path(repo_fs_path)
        evidence = EvidenceLedgerWriter(task_id=request.task_id, run_id=request.run_id)
        context = ChainContext(
            request=request,
            store=store,
            evidence=evidence,
            repo_fs_path=repo_fs_path,
            manifest=manifest,
            scrum=scrum,
            repo_snapshot=snapshot_repo(repo_fs_path) if repo_fs_path.exists() else {},
            agent_specs=agent_specs or [],
            agent_adapters=agent_adapters or {},
            tool_registry=tool_registry,
            tool_policy=tool_policy,
        )

        results: list[HandlerResult] = []
        pr_status = PrStatus.NOT_REQUIRED
        final_status = "PASS"
        stopped = False

        for index, handler_name in enumerate(chain.handler_names):
            handler = self.registry.get(handler_name)
            if handler is None:
                # Registered chain references a deferred handler: honest BLOCKED.
                results.append(
                    HandlerResult(
                        handler_name=handler_name,
                        handler_type=HandlerType.PURE_CHECK,
                        status=HandlerStatus.BLOCKED,
                        decision=HandlerDecision.BLOCKED,
                        failure_reasons=[f"handler not implemented: {handler_name} (deferred)"],
                    )
                )
                final_status = "BLOCKED"
                stopped = True
                self._checkpoint(context, store, index, handler_name, results[-1])
                break

            if not handler.can_handle(request):
                result = HandlerResult(
                    handler_name=handler_name,
                    handler_type=handler.handler_type,
                    status=HandlerStatus.SKIPPED,
                    decision=HandlerDecision.SKIP_NOT_APPLICABLE,
                    failure_reasons=["handler not applicable"],
                )
            else:
                result = handler.handle(request, context)
                result = self._enforce_no_repo_mutation(handler.handler_type, context, result)

            results.append(result)

            # Authority: only a VERIFIER handler may set the verifier decision.
            if can_decide_pass(handler.handler_type) and result.status in _STATUS_TO_DECISION:
                context.verifier_decision = _STATUS_TO_DECISION[result.status]

            pr_status = self._pr_status(result, pr_status)
            self._checkpoint(context, store, index, handler_name, result)

            if result.decision in (HandlerDecision.FAIL, HandlerDecision.BLOCKED):
                final_status = "FAIL" if result.decision == HandlerDecision.FAIL else "BLOCKED"
                stopped = True
                break
            if result.decision == HandlerDecision.STOP:
                break

        final_status = self._final_status(final_status, stopped, context, results)
        return ChainExecutionResult(
            run_id=request.run_id,
            task_id=request.task_id,
            task_type=request.task_type.value,
            chain_id=chain.chain_id,
            mode=request.mode,
            handler_results=results,
            final_status=final_status,
            verifier_decision=context.verifier_decision,
            eval_score=context.eval_score,
            pr_status=pr_status,
            agent_self_certification_used=context.agent_self_certification_used,
            auto_merge=False,
            auto_deploy=False,
            evidence_artifacts=list(context.artifacts),
        )

    # --- helpers ------------------------------------------------------------
    def _enforce_no_repo_mutation(
        self, handler_type: HandlerType, context: ChainContext, result: HandlerResult
    ) -> HandlerResult:
        """A handler whose type may not modify the repo must not have done so."""
        if can_modify_repo(handler_type) or not context.repo_fs_path.exists():
            return result
        if snapshot_repo(context.repo_fs_path) != context.repo_snapshot:
            return HandlerResult(
                handler_name=result.handler_name,
                handler_type=handler_type,
                status=HandlerStatus.BLOCKED,
                decision=HandlerDecision.BLOCKED,
                failure_reasons=[
                    f"authority violation: {handler_type.value} modified the repository"
                ],
            )
        return result

    def _pr_status(self, result: HandlerResult, current: PrStatus) -> PrStatus:
        value = result.metadata.get("pr_status")
        if value:
            return PrStatus(value)
        return current

    def _final_status(
        self, running: str, stopped: bool, context: ChainContext, results: list[HandlerResult]
    ) -> str:
        if stopped:
            return running
        # Completed the chain. PASS requires an independent verifier PASS.
        if context.verifier_decision == Decision.PASS:
            return "PASS"
        if context.verifier_decision == Decision.FAIL:
            return "FAIL"
        return "BLOCKED"

    def _checkpoint(
        self,
        context: ChainContext,
        store: ArtifactStore,
        index: int,
        handler_name: str,
        result: HandlerResult,
    ) -> None:
        checkpoint = Checkpoint(
            run_id=context.run_id,
            task_id=context.task_id,
            state="EXECUTE_CHAIN",
            next_action=handler_name,
            verifier_decision=context.verifier_decision,
            gate_results=result.gate_results,
        )
        write_checkpoint(
            store, checkpoint, name=f"checkpoint_{index:02d}_{handler_name}.json"
        )

    def _blocked_result(
        self, request: ChainRequest, *, chain_id: str, reasons: list[str]
    ) -> ChainExecutionResult:
        return ChainExecutionResult(
            run_id=request.run_id,
            task_id=request.task_id,
            task_type=request.task_type.value,
            chain_id=chain_id,
            mode=request.mode,
            handler_results=[],
            final_status="BLOCKED",
            verifier_decision=Decision.BLOCKED,
            pr_status=PrStatus.BLOCKED,
        )
