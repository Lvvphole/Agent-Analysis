"""Evaluation handlers (handoff Section 4 steps 16, 8 matrix).

The evaluator scores output quality but CANNOT override the verifier decision —
it only writes ``eval_score``. Memory updates are evidence-based or explicitly
skipped; never derived from agent narrative.
"""

from __future__ import annotations

import json

from app.chains.context import ChainContext
from app.constants import Decision
from app.handlers.base import Handler
from app.schemas.chain import ChainRequest, HandlerType


class EvaluatorHandler(Handler):
    name = "EvaluatorHandler"
    handler_type = HandlerType.EVALUATOR

    def handle(self, request: ChainRequest, context: ChainContext):
        # Score = share of ledger entries that did not record a failure. This is
        # advisory only; it never changes the verifier decision or final status.
        entries = context.evidence.ledger.ledger_entries
        non_fail = sum(1 for e in entries if e.result != "FAIL")
        score = round(non_fail / len(entries), 4) if entries else 0.0
        context.eval_score = score
        art = context.record_artifact(
            name="evaluation_report.json",
            data=json.dumps(
                {
                    "eval_score": score,
                    "verifier_decision": context.verifier_decision.value,
                    "note": "evaluator scores quality and cannot override the verifier",
                },
                indent=2,
            ),
            artifact_type="ANALYSIS_REPORT",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class MemoryUpdateHandler(Handler):
    name = "MemoryUpdateHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        if context.verifier_decision == Decision.PASS:
            art = context.record_artifact(
                name="memory_update_record.json",
                data=json.dumps(
                    {"source": "verified_evidence", "verifier_decision": "PASS"}, indent=2
                ),
                artifact_type="ANALYSIS_REPORT",
                recorded_by=self.name,
            )
        else:
            art = context.record_artifact(
                name="memory_update_skip_reason.json",
                data=json.dumps(
                    {"skipped": True, "reason": "no verifier PASS; memory not updated"},
                    indent=2,
                ),
                artifact_type="ANALYSIS_REPORT",
                recorded_by=self.name,
            )
        return self._ok(artifacts=[art.path])


HANDLERS = [
    EvaluatorHandler(),
    MemoryUpdateHandler(),
]
