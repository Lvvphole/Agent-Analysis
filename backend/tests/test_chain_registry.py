"""Chain registry tests (handoff Section 10, 16.1)."""

from __future__ import annotations

from app.chains.registry import (
    CHAIN_DEFINITIONS,
    TASK_TYPE_TO_CHAIN,
    resolve_chain,
)
from app.schemas.chain import TaskType


def test_known_task_type_resolves_to_correct_chain():
    assert resolve_chain("AI_READINESS_AUDIT").chain_id == "ai_readiness_audit_chain"
    assert resolve_chain("IMPLEMENTATION").chain_id == "implementation_chain"
    # REFACTOR / TEST_COVERAGE_EXPANSION reuse the implementation chain.
    assert resolve_chain("REFACTOR").chain_id == "implementation_chain"
    assert resolve_chain("TEST_COVERAGE_EXPANSION").chain_id == "implementation_chain"


def test_unknown_task_type_returns_none():
    assert resolve_chain("NOT_A_TASK") is None


def test_every_task_type_is_registered():
    for t in TaskType:
        assert t.value in TASK_TYPE_TO_CHAIN
        assert resolve_chain(t.value) is not None


def test_registered_chain_order_is_deterministic_and_immutable():
    chain = resolve_chain("AI_READINESS_AUDIT")
    # First control handlers in fixed order; ends at StopOrLoopHandler.
    assert chain.handler_names[0] == "ManifestValidationHandler"
    assert chain.handler_names[-1] == "StopOrLoopHandler"
    # Definitions are frozen tuples — a request cannot reorder them.
    assert isinstance(chain.handler_names, tuple)


def test_ai_readiness_chain_has_no_diff_capture():
    chain = resolve_chain("AI_READINESS_AUDIT")
    assert "DiffCaptureHandler" not in chain.handler_names


def test_implementation_chain_requires_diff_capture():
    chain = resolve_chain("IMPLEMENTATION")
    assert "DiffCaptureHandler" in chain.handler_names
    assert "ImplementationVerifierHandler" in chain.handler_names
    assert chain.handler_names.index("ImplementationVerifierHandler") > chain.handler_names.index(
        "DiffCaptureHandler"
    )
