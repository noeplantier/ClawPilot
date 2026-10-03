"""Rules for fetching a prospect's own public homepage: pure, no I/O. What may be requested, and what robots.txt says.

Only `http`/`https` on the default ports, no credentials in the URL, never a host that resolves to a private, loopback,
link-local or otherwise non-public address (SSRF), and never somebody else's platform (social networks, review sites,
directories): a prospect's own site only, and only where its robots.txt allows this crawler.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from services.outreach_os.normalize import THIRD_PARTY_HOSTS

# Platforms whose terms or technical measures forbid automated access: never fetched, whatever the listing says.
PLATFORM_HOSTS = THIRD_PARTY_HOSTS | {
    "linkedin.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "youtube.com",
    "pinterest.com",
    "glassdoor.com",
    "ubereats.com",
    "deliveroo.fr",
    "deliveroo.com",
    "booking.com",
    "airbnb.com",
}
INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")
MAX_URL_CHARS = 2048
DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class Target:
    scheme: str
    host: str
    port: int
    path: str  # path + query, always starting with "/"

    @property
    def url(self) -> str:
        default = DEFAULT_PORTS[self.scheme]
        netloc = self.host if self.port == default else f"{self.host}:{self.port}"
        return f"{self.scheme}://{netloc}{self.path}"

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.host}"


def parse_target(url: str) -> Target | None:
    """The request target, or None when the URL must not be fetched at all."""
    if not url or len(url) > MAX_URL_CHARS:
        return None
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if scheme not in DEFAULT_PORTS or not host or parts.username or parts.password:
        return None
    if port is not None and port != DEFAULT_PORTS[scheme]:
        return None
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return Target(scheme, host, DEFAULT_PORTS[scheme], path)


def blocked_host(host: str) -> bool:
    """True for platforms and for names that can only be internal."""
    if "." not in host or host.endswith(INTERNAL_SUFFIXES):
        return True
    return any(host == h or host.endswith("." + h) for h in PLATFORM_HOSTS)


def is_public_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return address.is_global and not address.is_multicast


def all_public(ips: list[str]) -> bool:
    """Every resolved address must be public: one private answer is enough to refuse (DNS rebinding tricks)."""
    return bool(ips) and all(is_public_ip(ip) for ip in ips)


def robots_decision(status: int | None, text: str | None, user_agent: str, url: str) -> bool:
    """May `user_agent` fetch `url`, given how `/robots.txt` answered?

    Conservative: a missing file (404/410) allows; a file we cannot read (network error, 5xx, 401/403, anything else
    unexpected) forbids, because "unknown" is not permission.
    """
    if status in (404, 410):
        return True
    if status is None or status != 200 or text is None:
        return False
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser.can_fetch(user_agent, url)
