"""Verifier handlers (handoff Section 11, 14).

VERIFIER is the only handler type permitted to decide PASS/FAIL/BLOCKED. The
executor maps a VERIFIER handler's status onto the run's verifier decision; no
other handler can. Verifiers aggregate the existing gates and never downgrade a
gate FAIL.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.chains.context import ChainContext
from app.gates.evidence_gate import evidence_gate
from app.gates.no_self_certification_gate import no_self_certification_gate
from app.gates.scope_gate import scope_gate
from app.gates.strategic_programming_gate import strategic_programming_gate
from app.gates.test_gate import test_gate
from app.constants import RunType
from app.handlers.base import Handler
from app.schemas.chain import ChainRequest, HandlerType
from app.schemas.gate_result import GateResult
from app.schemas.strategic_programming import StrategicProgramming


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_str(decision_pass: bool) -> str:
    return "PASS" if decision_pass else "FAIL"


class AnalysisVerifierHandler(Handler):
    name = "AnalysisVerifierHandler"
    handler_type = HandlerType.VERIFIER

    def handle(self, request: ChainRequest, context: ChainContext):
        context.verifier_run_id = context.verifier_run_id or "analysis-verifier"
        gates = [
            no_self_certification_gate(
                coding_agent_run_id=context.coding_agent_run_id,
                verifier_run_id=context.verifier_run_id,
            ),
            evidence_gate(
                context.evidence.ledger,
                run_id=context.run_id,
                task_id=context.task_id,
                required_artifact_types=("ANALYSIS_REPORT",),
            ),
        ]
        result = self._from_gates(gates)
        context.record_artifact(
            name="verifier_report.json",
            data=_analysis_report_json(context, gates),
            artifact_type="VERIFIER_REPORT",
            result="PASS" if result.status.value == "PASS" else "FAIL",
            recorded_by=self.name,
        )
        return result


class ImplementationVerifierHandler(Handler):
    name = "ImplementationVerifierHandler"
    handler_type = HandlerType.VERIFIER

    def handle(self, request: ChainRequest, context: ChainContext):
        context.verifier_run_id = context.verifier_run_id or "impl-verifier"
        tests_applicable = not request.metadata.get("tests_not_applicable")
        required = ("DIFF", "TEST") if tests_applicable else ("DIFF",)
        strategic = context.strategic or StrategicProgramming()

        gates: list[GateResult] = [
            no_self_certification_gate(
                coding_agent_run_id=context.coding_agent_run_id,
                verifier_run_id=context.verifier_run_id,
                agent_summary_used_as_evidence=not context.agent_summary_quarantined,
            ),
            test_gate(
                context.test_outcomes,
                run_type=RunType.IMPLEMENTATION,
                tests_applicable=tests_applicable,
            ),
            evidence_gate(
                context.evidence.ledger,
                run_id=context.run_id,
                task_id=context.task_id,
                required_artifact_types=required,
            ),
            strategic_programming_gate(strategic),
            scope_gate(
                context.changed_files,
                files_in_scope=request.scope.files_in_scope,
                files_out_of_scope=request.scope.files_out_of_scope,
            ),
        ]
        result = self._from_gates(gates)
        context.record_artifact(
            name="verifier_report.json",
            data=_impl_report_json(context, gates, tests_applicable),
            artifact_type="VERIFIER_REPORT",
            result="PASS" if result.status.value == "PASS" else "FAIL",
            recorded_by=self.name,
        )
        return result


def _analysis_report_json(context: ChainContext, gates: list[GateResult]) -> str:
    import json

    return json.dumps(
        {
            "task_id": context.task_id,
            "run_id": context.run_id,
            "verifier_run_id": context.verifier_run_id,
            "coding_agent_run_id": context.coding_agent_run_id,
            "same_agent_verifier_check": _status_str(
                context.verifier_run_id != context.coding_agent_run_id
            ),
            "decision": "PASS" if all(g.passed for g in gates) else "FAIL",
            "failure_reasons": [r for g in gates if not g.passed for r in g.reasons],
            "timestamp": _now(),
        },
        indent=2,
    )


def _impl_report_json(context: ChainContext, gates: list[GateResult], tests_applicable: bool) -> str:
    import json

    by_name = {g.gate_name: g for g in gates}
    return json.dumps(
        {
            "task_id": context.task_id,
            "run_id": context.run_id,
            "verifier_run_id": context.verifier_run_id,
            "coding_agent_run_id": context.coding_agent_run_id,
            "same_agent_verifier_check": _status_str(
                "no_self_certification_gate" in by_name
                and by_name["no_self_certification_gate"].passed
            ),
            "test_status": ("PASS" if by_name["test_gate"].passed else "FAIL")
            if tests_applicable
            else "NOT_APPLICABLE",
            "scope_status": _status_str(by_name["scope_gate"].passed),
            "evidence_status": _status_str(by_name["evidence_gate"].passed),
            "decision": "PASS" if all(g.passed for g in gates) else "FAIL",
            "failure_reasons": [r for g in gates if not g.passed for r in g.reasons],
            "timestamp": _now(),
        },
        indent=2,
    )


HANDLERS = [
    AnalysisVerifierHandler(),
    ImplementationVerifierHandler(),
]
