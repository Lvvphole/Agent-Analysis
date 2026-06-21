"""Retry budget (Section 6.9).

Bounded autonomy: when attempts are exhausted the run stops as BLOCKED rather
than looping forever.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import (
    DEFAULT_MAX_AGENT_ATTEMPTS,
    DEFAULT_MAX_VERIFIER_FAILURES,
)


@dataclass(frozen=True)
class RetryStatus:
    exhausted: bool
    status: str  # "CONTINUE" | "BLOCKED"
    reason: str = ""


def evaluate_retry_budget(
    *,
    agent_attempts: int,
    verifier_failures: int,
    max_agent_attempts: int = DEFAULT_MAX_AGENT_ATTEMPTS,
    max_verifier_failures: int = DEFAULT_MAX_VERIFIER_FAILURES,
    on_exhaustion: str = "BLOCKED",
) -> RetryStatus:
    """Return CONTINUE while budget remains, otherwise the exhaustion status."""
    if agent_attempts >= max_agent_attempts:
        return RetryStatus(True, on_exhaustion, "max_agent_attempts reached")
    if verifier_failures >= max_verifier_failures:
        return RetryStatus(True, on_exhaustion, "max_verifier_failures reached")
    return RetryStatus(False, "CONTINUE")
