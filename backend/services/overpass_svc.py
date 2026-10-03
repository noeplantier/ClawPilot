"""Overpass API client (OpenStreetMap data). Network I/O, only behind FEATURE_EXTERNAL_SOURCES.

Polite by construction: identified User-Agent, one request per search (several public servers tried in turn,
15 s each), 5 MB cap, a small in-memory cache
(10 min) so panning back and forth does not hit the public servers again, and a fallback to the next public instance
only on 429/502/503/504. No key, no account, nothing paid. Implements `Fetcher` so tests inject a fake: no socket is
ever opened in tests.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Protocol

from services.site_fetcher_svc import PRODUCT, user_agent

logger = logging.getLogger(__name__)

# Public, free instances. A shared cloud IP is sometimes throttled by one of them (the connection just hangs), so
# several are tried in turn; each gets a short timeout so that all fit under the host request limit (4 x 15 s).
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
TIMEOUT_SECONDS = 15.0
MAX_BYTES = 5_000_000
CACHE_SECONDS = 600
RETRY_STATUS = {429, 502, 503, 504}


class Unavailable(Exception):
    """The public Overpass servers did not answer usefully (busy, down, bad answer)."""


class Fetcher(Protocol):
    def __call__(self, query: str) -> dict[str, Any]: ...


def http_fetch(query: str) -> dict[str, Any]:
    body = urllib.parse.urlencode({"data": query}).encode()
    failures: list[str] = []
    for endpoint in ENDPOINTS:
        host = urllib.parse.urlparse(endpoint).hostname or endpoint
        request = urllib.request.Request(
            endpoint, data=body, headers={"User-Agent": user_agent() or PRODUCT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_SECONDS
            ) as response:  # noqa: S310 (https, fixed hosts)
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise Unavailable("answer too large: zoom in")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise Unavailable("unexpected answer")
            return payload
        except urllib.error.HTTPError as exc:
            failures.append(f"{host}: HTTP {exc.code}")
            if exc.code not in RETRY_STATUS:
                break
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            reason = getattr(
                exc, "reason", None
            )  # URLError wraps the socket/SSL/DNS cause: keep it, it says what to fix
            failures.append(
                f"{host}: {type(exc).__name__}" + (f" ({type(reason).__name__}: {reason})"[:120] if reason else "")
            )
    last = "; ".join(failures) or "no endpoint"
    logger.warning("overpass unavailable (%s)", last)
    raise Unavailable(f"OpenStreetMap servers are busy or unreachable ({last}); try again in a minute")


class CachedFetcher:
    def __init__(
        self, fetch: Callable[[str], dict[str, Any]] = http_fetch, clock: Callable[[], float] = time.monotonic
    ):
        self._fetch, self._clock = fetch, clock
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def __call__(self, query: str) -> dict[str, Any]:
        now = self._clock()
        hit = self._cache.get(query)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
        payload = self._fetch(query)
        if len(self._cache) > 200:
            self._cache.clear()
        self._cache[query] = (now, payload)
        return payload


default_fetcher = CachedFetcher()
