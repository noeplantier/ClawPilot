"""Overpass API client (OpenStreetMap data). Network I/O, only behind FEATURE_EXTERNAL_SOURCES.

Polite by construction: identified User-Agent, one request per search (several public servers tried in turn,
15 s each), 5 MB cap, a small in-memory cache
(10 min) so panning back and forth does not hit the public servers again, and a fallback to the next public instance
only on 429/502/503/504. No key, no account, nothing paid. Implements `Fetcher` so tests inject a fake: no socket is
ever opened in tests.
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
from typing import Any, Callable, Protocol

from services.outreach_os import map_jobs
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


def endpoints() -> tuple[str, ...]:
    """OVERPASS_ENDPOINTS (comma separated URLs) replaces the public list: a self-hosted Overpass, or a test double."""
    configured = tuple(u.strip() for u in os.environ.get("OVERPASS_ENDPOINTS", "").split(",") if u.strip())
    return configured or ENDPOINTS


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


def http_fetch(query: str) -> dict[str, Any]:
    body = urllib.parse.urlencode({"data": query}).encode()
    failures: list[str] = []
    kinds: list[str] = []
    for endpoint in endpoints():
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
                failures.append(f"{host}: unexpected answer")
                kinds.append("bad_answer")
                continue
            if "runtime error" in str(payload.get("remark", "")):
                # HTTP 200 but the query was cut short on the server: its (partial or empty) elements are not an answer
                failures.append(f"{host}: query timed out on the server")
                kinds.append("busy")
                continue
            return payload
        except urllib.error.HTTPError as exc:
            failures.append(f"{host}: HTTP {exc.code}")
            kinds.append(_kind_of_http(exc.code))
            if exc.code not in RETRY_STATUS:
                break
        except json.JSONDecodeError:
            failures.append(f"{host}: not JSON")
            kinds.append("bad_answer")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)  # URLError wraps the socket/SSL/DNS cause: it says what to fix
            failures.append(
                f"{host}: {type(exc).__name__}" + (f" ({type(reason).__name__}: {reason})"[:120] if reason else "")
            )
            kinds.append(
                "timeout" if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError) else "unreachable"
            )
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
