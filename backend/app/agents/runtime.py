"""Agent runtime — a single controlled, role-bound invocation.

Selects the declared model for a role, enforces allowlisting (only declared
specs are usable) and provider availability, invokes through an ``LLMAdapter``,
and records the call via the existing ``LLMInvocationRecorder`` (request +
response stored & hashed but NOT ledgered as proof; the structured
``LLMInvocationRecord`` is ledgered with ``used_as_evidence=False``).

If no model is bound to the role, or the provider is unavailable / fails, the
result is ``BLOCKED`` — never a fabricated PASS.
"""

from __future__ import annotations

from app.agents.provider import AgentInvocationRequest, AgentInvocationResult
from app.llm.base import LLMAdapter
from app.llm.recorder import LLMInvocationRecorder
from app.schemas.model_policy import ModelRole, ModelSpec


class AgentRuntime:
    def __init__(
        self,
        specs: list[ModelSpec],
        adapters: dict[str, LLMAdapter],
        recorder: LLMInvocationRecorder,
    ) -> None:
        self.specs = specs
        self.adapters = adapters
        self.recorder = recorder

    def _select(self, role: ModelRole) -> ModelSpec | None:
        return next((s for s in self.specs if s.role == role), None)

    def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        spec = self._select(request.role)
        if spec is None:
            return AgentInvocationResult(
                status="BLOCKED", reason=f"no model bound to role {request.role.value}"
            )
        if not request.prompt_hash:
            return AgentInvocationResult(status="BLOCKED", reason="prompt hash required")

        adapter = self.adapters.get(spec.provider)
        if adapter is None:
            return AgentInvocationResult(
                status="BLOCKED",
                reason=f"provider unavailable: no adapter for '{spec.provider}'",
                model_id_used=spec.model_id,
            )

        try:
            response = adapter.invoke(spec, request.prompt)
        except Exception as exc:  # noqa: BLE001 - provider failure must BLOCK, not pass
            return AgentInvocationResult(
                status="BLOCKED",
                reason=f"provider invocation failed: {exc}",
                model_id_used=spec.model_id,
            )

        record = self.recorder.record(spec, request.prompt, response)
        return AgentInvocationResult(
            status="OK",
            text=response.text,
            record=record,
            model_id_used=spec.model_id,
        )
