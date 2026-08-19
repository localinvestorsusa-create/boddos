"""Token-bucket rate limiter + failed-auth lockout.

Blunts brute-force against auth and abuse of expensive endpoints (model calls,
agent runs). Per-client (IP) buckets refill at a steady rate. A separate
failure counter locks a client out after too many auth failures.
"""
from __future__ import annotations

import time


class _Bucket:
    __slots__ = ("tokens", "last")

    def __init__(self, capacity: float):
        self.tokens = capacity
        self.last = time.monotonic()


class RateLimiter:
    def __init__(self, rate_per_sec: float = 5.0, capacity: float = 20.0,
                 lockout_threshold: int = 8, lockout_seconds: float = 300.0):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.lockout_threshold = lockout_threshold
        self.lockout_seconds = lockout_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._fails: dict[str, int] = {}
        self._locked: dict[str, float] = {}

    def allow(self, client: str, cost: float = 1.0) -> bool:
        now = time.monotonic()
        b = self._buckets.get(client)
        if b is None:
            b = self._buckets[client] = _Bucket(self.capacity)
        b.tokens = min(self.capacity, b.tokens + (now - b.last) * self.rate)
        b.last = now
        if b.tokens < cost:
            return False
        b.tokens -= cost
        return True

    def is_locked(self, client: str) -> bool:
        until = self._locked.get(client)
        if until is None:
            return False
        if time.monotonic() >= until:
            self._locked.pop(client, None)
            self._fails.pop(client, None)
            return False
        return True

    def record_failure(self, client: str) -> None:
        n = self._fails.get(client, 0) + 1
        self._fails[client] = n
        if n >= self.lockout_threshold:
            self._locked[client] = time.monotonic() + self.lockout_seconds

    def record_success(self, client: str) -> None:
        self._fails.pop(client, None)
        self._locked.pop(client, None)
