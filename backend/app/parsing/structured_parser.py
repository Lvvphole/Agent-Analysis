"""Structured output parser for the analysis agent.

Model output is *advisory context only*. This parser validates raw model text
against a strict schema and returns ``None`` on any malformed output — there is
no repair step in this slice (repair must be bounded, logged, and tested before
it is added). The parser cannot invent evidence: it only accepts or rejects.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError


class AnalysisAgentOutput(BaseModel):
    """Schema for the AI-readiness analysis agent's structured output.

    Advisory only: it never replaces the deterministic repo inventory, command
    discovery, evidence ledger, or verifier report.
    """

    model_config = {"extra": "forbid"}

    summary: str = ""
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = 0.0


def parse_structured_output(raw: str | None) -> AnalysisAgentOutput | None:
    """Parse + schema-validate raw model text. Returns ``None`` if malformed.

    No repair, no coercion beyond Pydantic's own typing. Malformed JSON, wrong
    shape, or extra keys all return ``None`` so the caller can BLOCK.
    """
    if not raw or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return AnalysisAgentOutput.model_validate(payload)
    except ValidationError:
        return None
