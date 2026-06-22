"""Handler base interface and registry (handoff Section 9).

A handler performs one bounded responsibility and returns a structured
``HandlerResult``. Handlers create artifacts via ``context.record_artifact``
(which hashes + records evidence) but never write checkpoints or set the
verifier decision directly — the executor (harness) owns those.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.chain import (
    ChainRequest,
    HandlerDecision,
    HandlerResult,
    HandlerStatus,
    HandlerType,
)
from app.schemas.gate_result import GateResult

# Forward reference only for typing; avoids a circular import at module load.
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.chains.context import ChainContext


class Handler(ABC):
    """Base class for all chain handlers."""

    name: str = "Handler"
    handler_type: HandlerType = HandlerType.PURE_CHECK

    def can_handle(self, request: ChainRequest) -> bool:
        return True

    @abstractmethod
    def handle(self, request: ChainRequest, context: "ChainContext") -> HandlerResult:
        ...

    # --- result builders (keep handler bodies to a single decision) ---------
    def _ok(
        self,
        *,
        decision: HandlerDecision = HandlerDecision.CONTINUE,
        artifacts: list[str] | None = None,
        gates: list[GateResult] | None = None,
        metadata: dict | None = None,
    ) -> HandlerResult:
        return HandlerResult(
            handler_name=self.name,
            handler_type=self.handler_type,
            status=HandlerStatus.PASS,
            decision=decision,
            artifacts_created=artifacts or [],
            gate_results=gates or [],
            metadata=metadata or {},
        )

    def _fail(
        self,
        reasons: list[str],
        *,
        blocked: bool = False,
        gates: list[GateResult] | None = None,
        corrections: list[str] | None = None,
    ) -> HandlerResult:
        status = HandlerStatus.BLOCKED if blocked else HandlerStatus.FAIL
        decision = HandlerDecision.BLOCKED if blocked else HandlerDecision.FAIL
        return HandlerResult(
            handler_name=self.name,
            handler_type=self.handler_type,
            status=status,
            decision=decision,
            gate_results=gates or [],
            failure_reasons=reasons,
            required_corrections=corrections or [],
        )

    def _skip(self, reason: str) -> HandlerResult:
        return HandlerResult(
            handler_name=self.name,
            handler_type=self.handler_type,
            status=HandlerStatus.SKIPPED,
            decision=HandlerDecision.SKIP_NOT_APPLICABLE,
            failure_reasons=[reason],
        )

    def _from_gates(
        self, gates: list[GateResult], *, blocked_on_fail: bool = False
    ) -> HandlerResult:
        """PASS if every gate passed, else FAIL (or BLOCKED)."""
        reasons = [r for g in gates if not g.passed for r in g.reasons]
        if reasons:
            return self._fail(reasons, blocked=blocked_on_fail, gates=gates)
        return self._ok(gates=gates)


class HandlerRegistry:
    """Maps handler name -> singleton handler instance."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, handler: Handler) -> None:
        self._handlers[handler.name] = handler

    def get(self, name: str) -> Handler | None:
        return self._handlers.get(name)

    def has(self, name: str) -> bool:
        return name in self._handlers

    def names(self) -> list[str]:
        return sorted(self._handlers)


def build_default_registry() -> HandlerRegistry:
    """Register every implemented handler. Deferred handlers are intentionally
    absent; the executor BLOCKS when a chain references one."""
    # Imported here to avoid import cycles (handlers import schemas/gates).
    from app.handlers import (
        analysis,
        ci_failure,
        control,
        dependency,
        documentation,
        evaluation,
        implementation,
        pr,
        security,
        verification,
    )

    registry = HandlerRegistry()
    for module in (control, analysis, implementation, verification, evaluation, pr, documentation, ci_failure, dependency, security):
        for handler in module.HANDLERS:
            registry.register(handler)
    return registry
