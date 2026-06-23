"""Manual analysis provider (caller-supplied output).

The ManualAdapter path mirrors the rest of the harness: instead of a live model
call, the caller supplies the model output out-of-band (keyed by model_id). This
keeps execution deterministic and keyless while still routing the output through
quarantine, parsing, hashing, and the invocation recorder.
"""

from __future__ import annotations

from app.llm.base import LLMAdapter, LLMResponse
from app.schemas.model_policy import ModelSpec


class ManualAnalysisAdapter(LLMAdapter):
    provider = "manual"

    def __init__(self, outputs: dict[str, str] | None = None, *, default: str = "") -> None:
        # outputs maps model_id -> raw response text the caller supplies.
        self.outputs = outputs or {}
        self.default = default

    def invoke(self, spec: ModelSpec, prompt: str) -> LLMResponse:
        text = self.outputs.get(spec.model_id, self.default)
        if not text:
            raise RuntimeError(f"no manual output supplied for {spec.model_id}")
        return LLMResponse(text=text, tokens_in=len(prompt.split()), tokens_out=len(text.split()))
