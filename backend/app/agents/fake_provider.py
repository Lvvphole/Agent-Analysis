"""Deterministic fake analysis provider (no network).

Returns valid, schema-shaped structured JSON for the analyst role so the full
runtime spine (invoke -> quarantine -> parse) can be exercised deterministically
in tests and in keyless environments. Output is advisory context only and never
becomes evidence. Real provider adapters implement the same ``LLMAdapter``.
"""

from __future__ import annotations

import json

from app.llm.base import LLMAdapter, LLMResponse
from app.schemas.model_policy import ModelSpec


class FakeAnalysisAdapter(LLMAdapter):
    provider = "fake"

    def invoke(self, spec: ModelSpec, prompt: str) -> LLMResponse:
        payload = {
            "summary": "Deterministic stub analysis of repository AI-readiness.",
            "risks": [
                "Stub provider in use; no live model reasoning performed.",
            ],
            "recommended_actions": [
                "Wire a real, allowlisted provider before relying on agent narrative.",
            ],
            "confidence": 0.5,
        }
        text = json.dumps(payload)
        return LLMResponse(text=text, tokens_in=len(prompt.split()), tokens_out=len(text.split()))
