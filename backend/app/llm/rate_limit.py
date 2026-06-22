"""Deterministic token-bucket rate limiter.

The clock is injectable so rate limiting is fully testable without sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    def __init__(self, requests_per_min: int, *, clock: Callable[[], float] | None = None) -> None:
        self.capacity = float(requests_per_min)
        self.tokens = float(requests_per_min)
        self.refill_per_sec = requests_per_min / 60.0
        self._clock = clock or time.monotonic
        self._last = self._clock()

    def allow(self) -> bool:
        """Consume one token if available; refill based on elapsed time."""
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
