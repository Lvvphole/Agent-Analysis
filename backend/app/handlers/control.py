"""Control handlers (handoff Section 11, 14).

Thin, deterministic wrappers that delegate to the existing hard gates. They
never re-implement or weaken gate logic.
"""

from __future__ import annotations

from app.chains.context import ChainContext
from app.constants import Decision, RunType
from app.gates.evidence_gate import evidence_gate
from app.gates.manifest_gate import manifest_gate
from app.gates.scrum_gate import scrum_gate
from app.handlers.base import Handler
from app.schemas.chain import (
    ChainRequest,
    HandlerDecision,
    HandlerType,
)
from app.schemas.gate_result import GateResult
from app.schemas.scrum_mapping import ScrumMapping


class ManifestValidationHandler(Handler):
    name = "ManifestValidationHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        gates: list[GateResult] = []
        # Envelope-level canonical + hard-rule validation.
        envelope = GateResult.of("chain_envelope", request.canonical_violations())
        gates.append(envelope)
        # Reuse the strict manifest gate when a full manifest is supplied.
        if context.manifest is not None:
            gates.append(manifest_gate(context.manifest))
            context.coding_agent_run_id = context.manifest.coding_agent_run_id
            context.verifier_run_id = context.manifest.verifier_run_id
        return self._from_gates(gates)


class ScrumMappingHandler(Handler):
    name = "ScrumMappingHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        mapping = context.scrum or ScrumMapping(
            product_backlog_item_id=request.scrum.product_backlog_item_id,
            sprint_goal=request.scrum.sprint_goal,
            sprint_backlog_task_id=request.scrum.sprint_backlog_task_id,
            acceptance_criteria=request.scrum.acceptance_criteria,
            definition_of_done_version=request.scrum.definition_of_done_version,
        )
        context.scrum = mapping
        gate = scrum_gate(
            mapping, locked_definition_of_done_version=context.locked_dod_version
        )
        return self._from_gates([gate])


class DefinitionOfDoneLockHandler(Handler):
    name = "DefinitionOfDoneLockHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        version = request.scrum.definition_of_done_version
        if not version:
            return self._fail(["Definition of Done version missing"])
        if context.locked_dod_version is None:
            context.locked_dod_version = version
        elif context.locked_dod_version != version:
            return self._fail(["Definition of Done changed mid-run"])
        context.record_artifact(
            name="definition_of_done_lock.json",
            data=f'{{"definition_of_done_version": "{context.locked_dod_version}"}}',
            artifact_type="SCRUM_MAPPING",
            recorded_by=self.name,
        )
        return self._ok()


class ScopeValidationHandler(Handler):
    name = "ScopeValidationHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        # Implementation work must declare an explicit in-scope allowlist;
        # read-only analysis may operate on the whole repo.
        if request.mode == RunType.IMPLEMENTATION and not request.scope.files_in_scope:
            return self._fail(["files_in_scope empty for implementation run"])
        return self._ok()


class EvidenceGateHandler(Handler):
    name = "EvidenceGateHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        if request.mode == RunType.IMPLEMENTATION:
            # Tests may be a documented NOT_APPLICABLE; then only a diff is required.
            required = ("DIFF",) if request.metadata.get("tests_not_applicable") else ("DIFF", "TEST")
        else:
            required = ("ANALYSIS_REPORT",)
        gate = evidence_gate(
            context.evidence.ledger,
            run_id=context.run_id,
            task_id=context.task_id,
            required_artifact_types=required,
        )
        return self._from_gates([gate])


class StopOrLoopHandler(Handler):
    name = "StopOrLoopHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        # Terminal handler: finalize the evidence ledger with the run decision.
        decision = context.verifier_decision
        final = decision if decision != Decision.PENDING else Decision.BLOCKED
        context.evidence.finalize(final)
        return self._ok(decision=HandlerDecision.STOP)


HANDLERS = [
    ManifestValidationHandler(),
    ScrumMappingHandler(),
    DefinitionOfDoneLockHandler(),
    ScopeValidationHandler(),
    EvidenceGateHandler(),
    StopOrLoopHandler(),
]
