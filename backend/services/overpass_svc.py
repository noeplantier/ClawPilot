"""Overpass API client (OpenStreetMap data). Network I/O, only behind FEATURE_EXTERNAL_SOURCES.

Polite by construction: identified User-Agent, one request per search, 15 s per server, 5 MB cap, a small in-memory
cache (10 min) so panning back and forth does not hit the public servers again. No key, no account, nothing paid.
Implements `Fetcher` so tests inject a fake: no socket is ever opened in tests.

Resilient by construction: the public servers are tried in turn, a server that refuses us (403, 429, 5xx, connection
refused, timeout) is skipped for a while, only a 400 (our own bad query) stops the search, and a server that is merely
slow is *hedged*: after HEDGE_SECONDS a second server is asked too (never more than MAX_PARALLEL at once) and the first
valid answer wins. A relay (OVERPASS_RELAY_URL: the Netlify function of this application, or any Overpass-compatible
URL) comes first.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Protocol

from services.outreach_os import map_jobs
from services.site_fetcher_svc import PRODUCT, user_agent

logger = logging.getLogger(__name__)

# Public, free instances. A shared cloud IP is often refused or throttled by some of them (measured from the
# production host: connection refused, read timeouts, 504), so several are tried in turn, each with a short timeout.
# The job runs in the background: the total (5 x 15 s at worst) only has to stay under the 3 minutes after which a job
# counts as lost.
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
TIMEOUT_SECONDS = 15.0
HEDGE_SECONDS = 4.0  # a server silent for this long gets a second one asked beside it (the first keeps running)
MAX_PARALLEL = 2  # never more than this many requests in flight for one search: polite to the public servers
COOLDOWN_SECONDS = (
    300.0  # a server that just failed is tried last for this long, so the next search does not wait on it
)
_cooldown: dict[str, float] = {}
_clock = time.monotonic


def reset_cooldown() -> None:
    _cooldown.clear()


def ordered(candidates: tuple[str, ...]) -> list[str]:
    """Servers that did not fail recently first (configured order kept), the cooling ones after: none is skipped."""
    now = _clock()
    ready = [e for e in candidates if _cooldown.get(e, 0.0) <= now]
    return ready + [e for e in candidates if e not in ready]


def _cool(endpoint: str) -> None:
    _cooldown[endpoint] = _clock() + COOLDOWN_SECONDS


def cooling_hosts() -> list[str]:
    now = _clock()
    return sorted(urllib.parse.urlparse(e).hostname or e for e, until in _cooldown.items() if until > now)


def endpoints() -> tuple[str, ...]:
    """OVERPASS_ENDPOINTS (comma separated URLs) replaces the public list: a self-hosted Overpass, or a test double."""
    configured = tuple(u.strip() for u in os.environ.get("OVERPASS_ENDPOINTS", "").split(",") if u.strip())
    return configured or (_relay() + ENDPOINTS)


def _relay() -> tuple[str, ...]:
    """OVERPASS_RELAY_URL: an https Overpass-compatible URL that reaches the public servers from another address (the
    Netlify function of this application). It is tried first; anything that is not an https URL is ignored."""
    url = os.environ.get("OVERPASS_RELAY_URL", "").strip()
    parsed = urllib.parse.urlparse(url)
    return (url,) if parsed.scheme == "https" and parsed.hostname else ()


MAX_BYTES = 5_000_000
CACHE_SECONDS = 600
RETRY_STATUS = {429, 502, 503, 504}


class _IPv4Connection(http.client.HTTPSConnection):
    """The API's host has no IPv6 route ("Network is unreachable"): resolve and connect over IPv4 only."""

    def connect(self) -> None:
        last: OSError = OSError("no IPv4 address")
        for family, kind, proto, _, address in socket.getaddrinfo(
            self.host, self.port, socket.AF_INET, socket.SOCK_STREAM
        ):
            sock = socket.socket(family, kind, proto)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)
            except OSError as exc:
                sock.close()
                last = exc
                continue
            self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            return
        raise last


class _IPv4Handler(urllib.request.HTTPSHandler):
    def https_open(self, req):  # type: ignore[no-untyped-def]
        return self.do_open(_IPv4Connection, req)


_opener = urllib.request.build_opener(_IPv4Handler)


def _open(request: urllib.request.Request, timeout: float):  # type: ignore[no-untyped-def]
    return _opener.open(request, timeout=timeout)


class Unavailable(Exception):
    """The public Overpass servers did not answer usefully (busy, down, bad answer).

    `code` is one of map_jobs.ERROR_CODES, `failures` names each server and what it did (safe to show: hosts only)."""

    def __init__(self, message: str, code: str = "overpass_unreachable", failures: tuple[str, ...] = ()):
        super().__init__(message)
        self.code = code
        self.failures = failures


class Fetcher(Protocol):
    def __call__(self, query: str) -> dict[str, Any]: ...


def _kind_of_http(status: int) -> str:
    return "busy" if status in RETRY_STATUS else "unreachable"


_Outcome = tuple[dict[str, Any] | None, str, str, bool]  # (payload, failure text, failure kind, our query is at fault)


def _ask(endpoint: str, body: bytes) -> _Outcome:
    """One request to one server. Never raises for a server's own refusal: it returns what happened. Does not touch the
    shared cooldown table (the caller does, from one thread)."""
    host = urllib.parse.urlparse(endpoint).hostname or endpoint
    request = urllib.request.Request(
        endpoint, data=body, headers={"User-Agent": user_agent() or PRODUCT, "Accept": "application/json"}
    )
    try:
        with _open(request, TIMEOUT_SECONDS) as response:  # noqa: S310 (https, fixed hosts)
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise Unavailable("answer too large: zoom in", code="overpass_too_large")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            return None, f"{host}: unexpected answer", "bad_answer", False
        if "runtime error" in str(payload.get("remark", "")):
            # HTTP 200 but the query was cut short on the server: its (partial or empty) elements are not an answer
            return None, f"{host}: query timed out on the server", "busy", False
        return payload, "", "", False
    except urllib.error.HTTPError as exc:
        # 400 = our query is wrong (every server would say so). 403/401/406/451 = THIS server refuses us (blocked
        # address, policy): the next one may well answer, so it is skipped, never a reason to stop the search.
        return None, f"{host}: HTTP {exc.code}", _kind_of_http(exc.code), exc.code == 400
    except json.JSONDecodeError:
        return None, f"{host}: not JSON", "bad_answer", False
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None)  # URLError wraps the socket/SSL/DNS cause: it says what to fix
        failure = f"{host}: {type(exc).__name__}" + (f" ({type(reason).__name__}: {reason})"[:120] if reason else "")
        timed_out = isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
        return None, failure, "timeout" if timed_out else "unreachable", False


def http_fetch(query: str) -> dict[str, Any]:
    body = urllib.parse.urlencode({"data": query}).encode()
    queue = list(ordered(endpoints()))
    failures: list[str] = []
    kinds: list[str] = []
    pending: dict[Future[_Outcome], str] = {}
    pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL, thread_name_prefix="overpass")

    def launch() -> None:
        endpoint = queue.pop(0)
        pending[pool.submit(_ask, endpoint, body)] = endpoint

    try:
        if queue:
            launch()
        stop = False
        while pending and not stop:
            # a server that is merely slow is hedged: after HEDGE_SECONDS the next one is asked beside it
            hedge = bool(queue) and len(pending) < MAX_PARALLEL
            done, _ = wait(list(pending), timeout=HEDGE_SECONDS if hedge else None, return_when=FIRST_COMPLETED)
            if not done:
                launch()
                continue
            for future in done:
                endpoint = pending.pop(future)
                payload, failure, kind, at_fault = future.result()  # re-raises Unavailable("answer too large")
                if payload is not None:
                    _cooldown.pop(endpoint, None)
                    return payload
                failures.append(failure)
                kinds.append(kind)
                if at_fault:
                    stop = True  # our own bad request: asking the other servers cannot help
                else:
                    _cool(endpoint)
            if queue and not pending and not stop:
                launch()  # the failed server is replaced by the next one, in turn
    finally:
        # the slower request of a hedged pair may still be running: it ends by itself at TIMEOUT_SECONDS, nobody
        # waits for it
        pool.shutdown(wait=False, cancel_futures=True)
    last = "; ".join(failures) or "no endpoint"
    logger.warning("overpass unavailable (%s)", last)
    raise Unavailable(
        f"OpenStreetMap servers are busy or unreachable ({last}); try again in a minute",
        code=map_jobs.classify_failures(kinds),
        failures=tuple(failures),
    )


def probe(endpoint: str, timeout: float = 6.0) -> dict[str, Any]:
    """One polite GET of the server's status page (no query): is it reachable from here, and how fast."""
    status_url = endpoint.replace("/interpreter", "/status")
    host = urllib.parse.urlparse(endpoint).hostname or endpoint
    started = time.monotonic()
    request = urllib.request.Request(status_url, headers={"User-Agent": user_agent() or PRODUCT})
    try:
        with _open(request, timeout) as response:  # noqa: S310 (https, fixed hosts)
            response.read(2000)
            code = int(response.status)
        return {"host": host, "ok": 200 <= code < 300, "status": code, "ms": int((time.monotonic() - started) * 1000)}
    except urllib.error.HTTPError as exc:
        return {"host": host, "ok": False, "status": exc.code, "ms": int((time.monotonic() - started) * 1000)}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return {
            "host": host,
            "ok": False,
            "error": f"{type(reason).__name__}: {reason}"[:160],
            "ms": int((time.monotonic() - started) * 1000),
        }


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
