"""Retry budget tests (Sections 6.9, 19)."""

from __future__ import annotations

from app.retry_budget import evaluate_retry_budget


def test_budget_remaining_continues():
    status = evaluate_retry_budget(agent_attempts=1, verifier_failures=0)
    assert status.exhausted is False
    assert status.status == "CONTINUE"


def test_agent_attempts_exhausted_blocks():
    status = evaluate_retry_budget(
        agent_attempts=3, verifier_failures=0, max_agent_attempts=3
    )
    assert status.exhausted is True
    assert status.status == "BLOCKED"


def test_verifier_failures_exhausted_blocks():
    status = evaluate_retry_budget(
        agent_attempts=0, verifier_failures=2, max_verifier_failures=2
    )
    assert status.exhausted is True
    assert status.status == "BLOCKED"
