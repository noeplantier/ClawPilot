"""Short-lived memory of what a discovery returned, so a page can be paged and a selection added without trusting the
client.

In memory, per process, 30 minutes, 200 runs: a miss means "search again" (410). The durable record of a discovery is
the audit log; the durable record of what was *added* is the prospect's sources (with the raw record and licence
note).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from services.outreach_os.types import RawListing

TTL_SECONDS = 1800
MAX_RUNS = 200


@dataclass
class Run:
    id: uuid.UUID
    account_id: uuid.UUID
    provider: str
    vertical: str
    country: str | None
    listings: list[RawListing]
    duplicates_merged: int
    truncated: bool
    created: float = field(default_factory=time.monotonic)


class RunStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._runs: dict[uuid.UUID, Run] = {}

    def put(self, run: Run) -> None:
        now = self._clock()
        for key in [k for k, v in self._runs.items() if now - v.created > TTL_SECONDS]:
            del self._runs[key]
        while len(self._runs) >= MAX_RUNS:
            del self._runs[next(iter(self._runs))]
        run.created = now
        self._runs[run.id] = run

    def get(self, account_id: uuid.UUID, run_id: uuid.UUID) -> Run | None:
        run = self._runs.get(run_id)
        if run is None or run.account_id != account_id or self._clock() - run.created > TTL_SECONDS:
            return None  # another organisation's run is indistinguishable from an unknown one
        return run


runs = RunStore()
