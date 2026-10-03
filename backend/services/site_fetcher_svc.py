"""Fetch a prospect's own public homepage, politely. Network I/O, only behind FEATURE_EXTERNAL_SOURCES.

Implements `SiteFetcher`. Every answer other than a clean HTTP response is "not checked" (None → the signals stay
UNKNOWN): robots.txt forbids or cannot be read, the host is a platform or non-public, the site answers
401/403/429/503 (an anti-bot or rate limit: never retried, never bypassed), a timeout, a non-HTML page, or the run
budget is spent.
Only a definite answer is reported: 2xx/3xx pages, 404/410/500/502/504, and a host name that does not exist.

Politeness: identified User-Agent, one request at a time, at least MIN_DELAY_SECONDS between two requests to the same
host, 8 s timeouts, 512 KiB cap, at most MAX_REDIRECTS redirects (each hop re-validated, robots included), and a
budget of MAX_FETCHES homepages / DEADLINE_SECONDS per run. The address that was validated is the address that is
connected to (no second DNS lookup between check and use). No cookies, no JavaScript, no login, no form.
"""

from __future__ import annotations

import http.client
import logging
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin

from services.outreach_os import urlguard
from services.outreach_os.drafts import SenderIdentity
from services.outreach_os.types import SiteSnapshot

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8.0
MAX_BYTES = 524288
MAX_REDIRECTS = 3
MAX_FETCHES = 25
DEADLINE_SECONDS = 60.0
MIN_DELAY_SECONDS = 2.0
PRODUCT = "PlantiersOutreachOS/1.0"
DEFINITE_ERRORS = {404, 410, 500, 502, 504}
NOT_CHECKED = {401, 403, 407, 408, 429, 451, 503}  # access refused or throttled: respect it, conclude nothing


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class TransportError(Exception):
    """`kind` is `dns` (the host name does not exist) or `other` (timeout, refused, TLS, reset…)."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


Resolver = Callable[[str], list[str]]
Transport = Callable[[urlguard.Target, str, dict[str, str]], RawResponse]


def system_resolver(host: str) -> list[str]:
    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})
    except socket.gaierror as exc:
        raise TransportError("dns" if exc.errno in (socket.EAI_NONAME, getattr(socket, "EAI_NODATA", -5)) else "other")
    except OSError:
        raise TransportError("other")


class _PinnedConnection(http.client.HTTPConnection):
    """Connects to the already validated IP, but speaks (and, for TLS, verifies) the real host name."""

    def __init__(self, target: urlguard.Target, ip: str) -> None:
        super().__init__(target.host, target.port, timeout=TIMEOUT_SECONDS)
        self._target, self._ip = target, ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self._target.port), timeout=TIMEOUT_SECONDS)
        if self._target.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self._target.host)
        self.sock = sock


def http_transport(target: urlguard.Target, ip: str, headers: dict[str, str]) -> RawResponse:
    conn = _PinnedConnection(target, ip)
    try:
        conn.request("GET", target.path, headers=headers)
        response = conn.getresponse()
        body = response.read(MAX_BYTES + 1)
        return RawResponse(response.status, {k.lower(): v for k, v in response.getheaders()}, body)
    except ssl.SSLError:
        raise TransportError("other")
    except (OSError, http.client.HTTPException):
        raise TransportError("other")
    finally:
        conn.close()


def user_agent() -> str:
    sender = SenderIdentity.from_env()
    return f"{PRODUCT} (+{sender.reply_to})" if sender else PRODUCT


class HttpSiteFetcher:
    """One instance per discovery run: it holds the run's budget, the robots.txt cache and the per-host clock."""

    def __init__(
        self,
        *,
        resolver: Resolver = system_resolver,
        transport: Transport = http_transport,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolver, self._transport, self._sleep, self._clock = resolver, transport, sleep, clock
        self._agent = user_agent()
        self._started = clock()
        self._fetches = 0
        self._robots: dict[str, Optional[tuple[int | None, str | None]]] = {}
        self._last_hit: dict[str, float] = {}

    # ------------------------------------------------------------------ one polite request
    def _get(self, target: urlguard.Target, ip: str, accept: str) -> RawResponse:
        wait = MIN_DELAY_SECONDS - (self._clock() - self._last_hit.get(target.host, -MIN_DELAY_SECONDS))
        if wait > 0:
            self._sleep(wait)
        self._last_hit[target.host] = self._clock()
        headers = {"User-Agent": self._agent, "Accept": accept, "Accept-Encoding": "identity", "Connection": "close"}
        return self._transport(target, ip, headers)

    def _public_ip(self, host: str) -> str | None:
        try:
            ips = self._resolver(host)
        except TransportError:
            raise
        return ips[0] if urlguard.all_public(ips) else None

    def _robots_allows(self, target: urlguard.Target, ip: str) -> bool:
        if target.origin not in self._robots:
            robots = urlguard.Target(target.scheme, target.host, target.port, "/robots.txt")
            try:
                resp = self._get(robots, ip, "text/plain")
                text = resp.body[:MAX_BYTES].decode("utf-8", "replace") if resp.status == 200 else None
                self._robots[target.origin] = (resp.status, text)
            except TransportError:
                self._robots[target.origin] = (None, None)
        status, text = self._robots[target.origin] or (None, None)
        return urlguard.robots_decision(status, text, PRODUCT, target.url)

    def _skip(self, why: str, host: str) -> None:
        logger.info("site not checked (%s): %s", why, host)

    # ------------------------------------------------------------------ SiteFetcher
    def fetch(self, url: str) -> SiteSnapshot | None:
        if self._fetches >= MAX_FETCHES or self._clock() - self._started > DEADLINE_SECONDS:
            return None  # run budget spent: the remaining sites are simply not checked
        target = urlguard.parse_target(url)
        if target is None or urlguard.blocked_host(target.host):
            return None
        self._fetches += 1
        for _ in range(MAX_REDIRECTS + 1):
            try:
                ip = self._public_ip(target.host)
            except TransportError as exc:
                if exc.kind == "dns":  # the name does not exist: a definite answer, reported as such
                    return SiteSnapshot(url=url, status=None, error="host name does not resolve")
                self._skip("dns error", target.host)
                return None
            if ip is None:
                self._skip("non-public address", target.host)
                return None
            if not self._robots_allows(target, ip):
                self._skip("robots.txt", target.host)
                return None
            try:
                resp = self._get(target, ip, "text/html,application/xhtml+xml")
            except TransportError:
                self._skip("connection", target.host)
                return None
            if resp.status in (301, 302, 303, 307, 308):
                nxt = urlguard.parse_target(urljoin(target.url, resp.headers.get("location", "")))
                if nxt is None or urlguard.blocked_host(nxt.host):
                    return None
                target = nxt
                continue
            if resp.status in NOT_CHECKED:
                self._skip(f"HTTP {resp.status}", target.host)
                return None
            if resp.status in DEFINITE_ERRORS:
                return SiteSnapshot(url=url, status=resp.status, error=f"HTTP {resp.status}")
            if not 200 <= resp.status < 300:
                return None
            if "html" not in resp.headers.get("content-type", "").lower() or len(resp.body) > MAX_BYTES:
                return None
            return SiteSnapshot(url=url, status=resp.status, html=resp.body.decode("utf-8", "replace"))
        return None  # too many redirects
