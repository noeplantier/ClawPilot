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


def scope(*, live: bool, sandbox_on: bool, entries: int) -> tuple[str, str]:
    """(code, sentence for the operator) saying who would REALLY receive a message with this configuration.

    The allowlist only restricts recipients while the sandbox is on. With the sandbox off it is inert, whatever it
    contains: the sentence says so, so nobody reads "2 allowed addresses" as a limit that is not applied."""
    if not live:
        return "dry_run", "Envoi réel désactivé : rien ne part, la liste blanche ne sert à rien."
    if sandbox_on and entries == 0:
        return "sandbox_empty", "Bac à sable actif et liste blanche vide : personne ne recevra de message."
    if sandbox_on:
        return (
            "sandbox_allowlist",
            f"Bac à sable actif : seuls les {entries} destinataire(s) de la liste blanche reçoivent un message.",
        )
    if entries:
        return (
            "allowlist_inactive",
            f"Bac à sable désactivé : la liste blanche ({entries} entrée(s)) est INACTIVE et ne restreint personne ; "
            "tout message approuvé partira réellement à son destinataire.",
        )
    return "open", "Bac à sable désactivé : tout message approuvé partira réellement à son destinataire."
