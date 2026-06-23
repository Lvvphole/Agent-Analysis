"""Structured output parser tests (runtime spine).

The parser is strict and repair-free: valid schema-shaped JSON parses; anything
malformed returns None so the caller can BLOCK. Agent output is advisory only.
"""

from __future__ import annotations

import json

from app.parsing.structured_parser import AnalysisAgentOutput, parse_structured_output


def test_valid_output_parses():
    raw = json.dumps(
        {"summary": "ok", "risks": ["r1"], "recommended_actions": ["a1"], "confidence": 0.4}
    )
    parsed = parse_structured_output(raw)
    assert isinstance(parsed, AnalysisAgentOutput)
    assert parsed.summary == "ok"
    assert parsed.confidence == 0.4


def test_partial_output_parses_with_defaults():
    parsed = parse_structured_output(json.dumps({"summary": "only summary"}))
    assert parsed is not None
    assert parsed.risks == [] and parsed.recommended_actions == []


def test_malformed_json_returns_none():
    assert parse_structured_output("not json at all") is None
    assert parse_structured_output("") is None
    assert parse_structured_output(None) is None


def test_non_object_json_returns_none():
    assert parse_structured_output(json.dumps([1, 2, 3])) is None
    assert parse_structured_output(json.dumps("a string")) is None


def test_extra_keys_rejected():
    raw = json.dumps({"summary": "x", "unexpected": "field"})
    assert parse_structured_output(raw) is None


def test_wrong_types_rejected():
    raw = json.dumps({"confidence": "high"})  # confidence must be float
    assert parse_structured_output(raw) is None
