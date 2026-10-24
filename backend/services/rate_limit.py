"""Sliding-window attempt limiter (in memory, per process) against password guessing and sign-up abuse.

Limits (override with the environment variables in brackets):
  - login: 10 failed attempts per e-mail address per 15 minutes, then 429 until the window passes
    [AUTH_MAX_FAILURES, AUTH_WINDOW_SECONDS]
  - register: 300 sign-ups per hour in total [REGISTER_MAX_PER_HOUR]

The keys are e-mail addresses (not IPs: behind a proxy the client address is not trustworthy), so an attacker can
lock a known address out for the window: that trade-off is accepted. State is per API process: with several
instances the effective limit is multiplied, and it resets on restart. A shared store (Redis) is the next step; see
docs/deployment.md.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Callable


class AttemptLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        *,
        max_keys: int = 50_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if not hits:
            self._hits.pop(key, None)
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds to wait before the next attempt is allowed; 0 when it is allowed now."""
        now = self._clock()
        hits = self._prune(key, now)
        if len(hits) < self.max_attempts:
            return 0
        return max(1, int(self.window - (now - hits[0])) + 1)

    def record(self, key: str) -> None:
        now = self._clock()
        if len(self._hits) >= self._max_keys and key not in self._hits:  # bounded memory: drop expired keys first
            for k in list(self._hits):
                self._prune(k, now)
            if len(self._hits) >= self._max_keys:
                self._hits.pop(next(iter(self._hits)))
        self._hits.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
        return value if value > 0 else default
    except ValueError:
        return default


login_failures = AttemptLimiter(_int_env("AUTH_MAX_FAILURES", 10), _int_env("AUTH_WINDOW_SECONDS", 900))
registrations = AttemptLimiter(_int_env("REGISTER_MAX_PER_HOUR", 300), 3600)
