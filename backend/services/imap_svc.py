"""IMAP reader for the sending mailbox (stdlib `imaplib`): detects replies and bounces.

Read-only apart from the \\Seen flag. Nothing runs unless IMAP_HOST, IMAP_USERNAME and IMAP_PASSWORD are all set
(`from_env()` is None otherwise: no partial default). TLS only (implicit SSL, port 993), certificate and host name
verified, timeouts on every operation. Messages are fetched with BODY.PEEK (reading never flags them) and only the
first MAX_BYTES of each; the caller flags them \\Seen after its transaction committed, so a crash re-reads (and
de-duplicates) instead of losing mail. The password is never logged or in `repr`.

    IMAP_HOST, IMAP_USERNAME, IMAP_PASSWORD   required
    IMAP_PORT                                 optional, default 993
    IMAP_FOLDER                               optional, default INBOX
"""

from __future__ import annotations

import imaplib
import logging
import os
import re
import ssl
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0
MAX_BYTES = 262144
_UID = re.compile(rb"UID (\d+)")


@dataclass(frozen=True)
class ImapConfig:
    host: str
    username: str
    password: str = field(repr=False)
    port: int = 993
    folder: str = "INBOX"

    @classmethod
    def from_env(cls) -> Optional["ImapConfig"]:
        host = os.environ.get("IMAP_HOST", "").strip()
        username = os.environ.get("IMAP_USERNAME", "").strip()
        password = os.environ.get("IMAP_PASSWORD", "")
        if not host or not username or not password:
            return None
        try:
            port = int(os.environ.get("IMAP_PORT", "").strip() or 993)
        except ValueError:
            return None
        if not 0 < port < 65536:
            return None
        return cls(host, username, password, port, os.environ.get("IMAP_FOLDER", "").strip() or "INBOX")


def is_configured() -> bool:
    return ImapConfig.from_env() is not None


def status() -> dict:
    """What Settings may show: never the username or the password."""
    config = ImapConfig.from_env()
    return {"configured": config is not None, "host": config.host if config else None}


class ImapMailbox:
    """`fetch_unseen` then `mark_seen`; each call opens and closes its own TLS connection."""

    def __init__(self, config: ImapConfig) -> None:
        self._config = config

    def _connect(self) -> imaplib.IMAP4_SSL:
        cfg = self._config
        client = imaplib.IMAP4_SSL(
            cfg.host, cfg.port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT_SECONDS
        )
        client.login(cfg.username, cfg.password)
        status_, _ = client.select(cfg.folder)  # read-write: needed to set \Seen later
        if status_ != "OK":
            client.logout()
            raise imaplib.IMAP4.error("cannot open the mailbox folder")
        return client

    def fetch_unseen(self, limit: int = 50) -> list[tuple[bytes, bytes]]:
        """(uid, raw message) for up to `limit` unseen messages, oldest first."""
        client = self._connect()
        try:
            status_, data = client.uid("SEARCH", "UNSEEN")
            if status_ != "OK" or not data or not data[0]:
                return []
            out: list[tuple[bytes, bytes]] = []
            for uid in data[0].split()[:limit]:
                status_, parts = client.uid("FETCH", uid.decode(), f"(BODY.PEEK[]<0.{MAX_BYTES}>)")
                if status_ != "OK":
                    continue
                for part in parts:
                    if isinstance(part, tuple) and isinstance(part[1], bytes):
                        out.append((uid, part[1]))
                        break
            return out
        finally:
            _close(client)

    def mark_seen(self, uids: list[bytes]) -> None:
        if not uids:
            return
        client = self._connect()
        try:
            for uid in uids:
                client.uid("STORE", uid.decode(), "+FLAGS", "(\\Seen)")
        finally:
            _close(client)


def _close(client: imaplib.IMAP4_SSL) -> None:
    try:
        client.close()
    except Exception:  # nothing to keep: closing is best effort
        pass
    try:
        client.logout()
    except Exception:
        pass


def mailbox_from_env() -> Optional[ImapMailbox]:
    config = ImapConfig.from_env()
    return ImapMailbox(config) if config else None
