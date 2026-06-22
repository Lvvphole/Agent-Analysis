"""Deterministic token-bucket rate limiter tests (injected clock, no sleeping)."""

from __future__ import annotations

from app.llm.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_allows_up_to_capacity_then_blocks():
    rl = RateLimiter(2, clock=FakeClock())
    assert rl.allow()
    assert rl.allow()
    assert not rl.allow()


def test_refills_on_injected_clock():
    clock = FakeClock()
    rl = RateLimiter(60, clock=clock)  # 1 token / second
    for _ in range(60):
        assert rl.allow()
    assert not rl.allow()
    clock.advance(1.0)
    assert rl.allow()
    assert not rl.allow()
