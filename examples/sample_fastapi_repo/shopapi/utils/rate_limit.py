"""Token-bucket rate limiter (not wired into the API yet).

A "token" here is a rate-limit permit, not an authentication token.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)
        self.clock = clock
        self.updated_at = clock()

    def _refill(self) -> None:
        now = self.clock()
        elapsed = now - self.updated_at
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = now

    def try_acquire(self, tokens: int = 1) -> bool:
        """Take ``tokens`` permits if available; return whether the request may proceed."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """One token bucket per client key (e.g. IP address or API token)."""

    def __init__(self, capacity: int = 10, refill_per_second: float = 1.0) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.buckets: dict[str, TokenBucket] = {}

    def allow(self, key: str) -> bool:
        bucket = self.buckets.setdefault(key, TokenBucket(self.capacity, self.refill_per_second))
        return bucket.try_acquire()
