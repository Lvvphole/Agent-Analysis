"""Agent provider contract.

Thin agent-level types over the existing controlled LLM layer
(``app.llm`` provides ``LLMAdapter``, ``ModelRouter``, ``LLMInvocationRecorder``;
``app.schemas.model_policy`` provides ``ModelSpec`` / ``ModelRole`` /
``LLMInvocationRecord``). These types describe a single controlled invocation
and the runtime configuration the executor threads into a chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.base import LLMAdapter
from app.schemas.model_policy import LLMInvocationRecord, ModelRole, ModelSpec
from app.storage.hashing import hash_bytes


@dataclass(frozen=True)
class AgentInvocationRequest:
    role: ModelRole
    prompt: str
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 23
    parallel_tool_calls: bool = False

    @property
    def prompt_hash(self) -> str:
        return hash_bytes(self.prompt.encode("utf-8"))


@dataclass
class AgentInvocationResult:
    status: str  # OK | BLOCKED
    text: str = ""
    record: LLMInvocationRecord | None = None
    reason: str = ""
    model_id_used: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "OK"


@dataclass
class AgentRuntimeConfig:
    """Declared models + provider adapters threaded into a chain run.

    Empty config => no agent is configured for the run (the agent step SKIPs and
    the deterministic chain remains the sole proof).
    """

    specs: list[ModelSpec] = field(default_factory=list)
    adapters: dict[str, LLMAdapter] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.specs)
