"""Deterministic stub LLM adapter (no network).

Used for tests and for environments without provider API keys. Real
``AnthropicAdapter`` / ``OpenAIAdapter`` implement the same ``LLMAdapter``
interface later.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.llm.base import LLMAdapter, LLMResponse
from app.schemas.model_policy import ModelSpec


class StubLLMAdapter(LLMAdapter):
    def __init__(self, provider: str = "stub", *, fail_for: Iterable[str] = ()) -> None:
        self.provider = provider
        self.fail_for = set(fail_for)

    def invoke(self, spec: ModelSpec, prompt: str) -> LLMResponse:
        if spec.model_id in self.fail_for:
            raise RuntimeError(f"stub failure for {spec.model_id}")
        text = f"[stub:{spec.model_id}] {prompt[:80]}"
        return LLMResponse(text=text, tokens_in=len(prompt.split()), tokens_out=8)
