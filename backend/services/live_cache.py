"""A tiny per-organisation answer cache keyed by a change token, for the views a page polls every few seconds.

The token (see `prospect_repo.change_token`) is computed from the database on every request; the answer behind it is
recomputed only when the token moved. An answer is never served under a newer token than the data it was built from,
so the worst case is one extra recomputation. In-process and bounded: a restart or another instance simply recomputes.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Hashable, Optional

MAX_ENTRIES = 64


class TokenCache:
    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._max = max_entries
        self._items: OrderedDict[Hashable, tuple[str, Any]] = OrderedDict()

    def get(self, key: Hashable, token: str) -> Optional[Any]:
        hit = self._items.get(key)
        if hit is None or hit[0] != token:
            return None
        self._items.move_to_end(key)
        return hit[1]

    def put(self, key: Hashable, token: str, value: Any) -> Any:
        self._items[key] = (token, value)
        self._items.move_to_end(key)
        while len(self._items) > self._max:
            self._items.popitem(last=False)
        return value

    def clear(self) -> None:
        self._items.clear()
