"""LLM adapter interface and role-aware router.

The router selects a model by role, enforces permission and rate-limit
pre-checks, records every invocation, and falls back to a declared fallback
model on throttle/failure. Real provider adapters implement the same
``LLMAdapter`` interface; the MVP ships only ``StubLLMAdapter``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.llm.rate_limit import RateLimiter
from app.llm.recorder import LLMInvocationRecorder
from app.schemas.model_policy import LLMInvocationRecord, ModelRole, ModelSpec


@dataclass
class LLMResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLMAdapter(ABC):
    provider: str = "abstract"

    @abstractmethod
    def invoke(self, spec: ModelSpec, prompt: str) -> LLMResponse:
        ...


@dataclass
class RouterResult:
    status: str  # OK | FALLBACK_USED | THROTTLED | PERMISSION_DENIED | NO_MODEL_FOR_ROLE
    record: LLMInvocationRecord | None = None
    reason: str = ""
    model_id_used: str = ""


class ModelRouter:
    """Routes a role to its declared model, gated by permission + rate limit."""

    def __init__(
        self,
        specs: list[ModelSpec],
        adapters: dict[str, LLMAdapter],
        recorder: LLMInvocationRecorder,
        *,
        rate_limiters: dict[str, RateLimiter] | None = None,
    ) -> None:
        self.specs = specs
        self.by_id = {s.model_id: s for s in specs}
        self.adapters = adapters
        self.recorder = recorder
        self.limiters = rate_limiters or {
            s.model_id: RateLimiter(max(1, s.rate_limit.requests_per_min)) for s in specs
        }

    def _select(self, role: ModelRole) -> ModelSpec | None:
        return next((s for s in self.specs if s.role == role), None)

    def invoke_role(
        self, role: ModelRole, prompt: str, *, require_permission: str | None = None
    ) -> RouterResult:
        spec = self._select(role)
        if spec is None:
            return RouterResult("NO_MODEL_FOR_ROLE", reason=f"no model bound to {role.value}")
        if require_permission and require_permission not in spec.permissions:
            return RouterResult(
                "PERMISSION_DENIED",
                reason=f"{spec.model_id} lacks permission: {require_permission}",
            )
        return self._invoke(spec, prompt, status="OK")

    def _invoke(self, spec: ModelSpec, prompt: str, *, status: str) -> RouterResult:
        limiter = self.limiters.get(spec.model_id)
        if limiter is not None and not limiter.allow():
            return self._fallback(spec, prompt, "THROTTLED", f"{spec.model_id} throttled")
        adapter = self.adapters.get(spec.provider)
        if adapter is None:
            return self._fallback(spec, prompt, "THROTTLED", f"no adapter for {spec.provider}")
        try:
            response = adapter.invoke(spec, prompt)
        except Exception as exc:  # noqa: BLE001 - fall back on any adapter failure
            return self._fallback(spec, prompt, "THROTTLED", f"{spec.model_id} failed: {exc}")
        record = self.recorder.record(spec, prompt, response, rate_limit_status=status)
        return RouterResult(status, record=record, model_id_used=spec.model_id)

    def _fallback(self, spec: ModelSpec, prompt: str, fail_status: str, reason: str) -> RouterResult:
        fb = self.by_id.get(spec.fallback_model_id) if spec.fallback_model_id else None
        if fb is None:
            return RouterResult(fail_status, reason=reason, model_id_used=spec.model_id)
        result = self._invoke(fb, prompt, status="FALLBACK_USED")
        if result.record is not None:
            result.status = "FALLBACK_USED"
        return result
