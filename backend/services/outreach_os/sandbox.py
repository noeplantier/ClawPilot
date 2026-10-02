"""Sandbox allowlist for live sending: pure, no I/O.

While the sandbox is on, a live adapter may only write to explicitly allowed recipients (your own addresses, a test
domain). An entry is a full address (`founder@plantiers.com`) or a domain (`@plantiers.com`, `plantiers.com`: that
domain only, subdomains excluded). An empty allowlist allows nobody: the sandbox fails closed.
"""

from __future__ import annotations

from services.outreach_os.normalize import normalize_email


def parse_allowlist(raw: str | None) -> tuple[str, ...]:
    """Comma, semicolon or whitespace separated entries, lower-cased, de-duplicated, order kept."""
    entries: list[str] = []
    for part in (raw or "").replace(";", ",").replace("\n", ",").replace(" ", ",").split(","):
        entry = part.strip().lower()
        if entry and entry not in entries:
            entries.append(entry)
    return tuple(entries)


def is_allowed(recipient: str, allowlist: tuple[str, ...]) -> bool:
    address = normalize_email(recipient)
    if address is None:
        return False
    domain = address.rsplit("@", 1)[1]
    return any(
        entry == address if "@" in entry.lstrip("@") else entry.lstrip("@") == domain for entry in allowlist if entry
    )
