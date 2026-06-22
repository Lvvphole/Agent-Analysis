"""PR handlers (handoff Section 11, 12.8, 13.8).

PR_ACTION handlers may report gated-PR readiness only after a verifier PASS.
They never merge and never deploy — there is no field, method, or path here that
could. ``auto_merge`` / ``auto_deploy`` are always false.
"""

from __future__ import annotations

import json

from app.chains.context import ChainContext
from app.constants import Decision
from app.gates.pr_gate import pr_gate
from app.handlers.base import Handler
from app.schemas.chain import ChainRequest, HandlerType, PrStatus

_GATED_PR_BODY = """# Gated Pull Request (candidate)

Run ID: {run_id}
Task ID: {task_id}
Verifier decision: {decision}

Auto-merge: NO
Auto-deploy: NO
Human or external authorized approval required: YES
"""


class PRGateHandler(Handler):
    name = "PRGateHandler"
    handler_type = HandlerType.PR_ACTION

    def handle(self, request: ChainRequest, context: ChainContext):
        decision = context.verifier_decision
        if decision != Decision.PASS:
            # Not ready: PR is only allowed after an independent verifier PASS.
            gate = pr_gate(verifier_decision=decision)
            return self._ok(
                gates=[gate],
                metadata={"pr_status": PrStatus.NOT_READY.value},
            )

        # Produce the gated PR body locally (no network). The PR stays gated.
        body = _GATED_PR_BODY.format(
            run_id=context.run_id, task_id=context.task_id, decision="PASS"
        )
        pr_body = context.record_artifact(
            name="pr_body.md", data=body, artifact_type="PR", recorded_by=self.name
        )
        gate = pr_gate(
            verifier_decision=decision,
            pr_skip_reason="local gated PR body written; remote push deferred",
            auto_merge=False,
            auto_deploy=False,
        )
        context.record_artifact(
            name="pr_gate_report.json",
            data=json.dumps(
                {
                    "pr_status": PrStatus.GATED.value,
                    "auto_merge": False,
                    "auto_deploy": False,
                    "human_approval_required": True,
                    "pr_gate": gate.model_dump(),
                },
                indent=2,
            ),
            artifact_type="PR",
            recorded_by=self.name,
        )
        return self._ok(
            artifacts=[pr_body.path],
            gates=[gate],
            metadata={"pr_status": PrStatus.GATED.value},
        )


class PRCreationHandler(Handler):
    name = "PRCreationHandler"
    handler_type = HandlerType.PR_ACTION

    def handle(self, request: ChainRequest, context: ChainContext):
        if context.verifier_decision != Decision.PASS:
            return self._skip("verifier PASS required before PR creation")
        art = context.record_artifact(
            name="pr_url.txt",
            data="PENDING: remote PR creation deferred; PR remains gated, no merge, no deploy",
            artifact_type="PR",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path], metadata={"pr_status": PrStatus.GATED.value})


HANDLERS = [
    PRGateHandler(),
    PRCreationHandler(),
]
