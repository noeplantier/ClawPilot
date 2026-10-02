"""Channel adapters: the only place a message could ever leave the system.

`ChannelAdapter` is a Protocol so a real provider can be added behind it later. Only `DryRunEmailAdapter` exists:
it validates the message and returns a deterministic result, and never opens a socket. Switching on live sending
without a real adapter must fail closed (see `select_adapter`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol

from services.outreach_os.normalize import normalize_email

_UNSUBSCRIBE_URL = re.compile(r"https?://\S+/api/unsubscribe/\S+")


@dataclass(frozen=True)
class ChannelMessage:
    to: str
    subject: str
    body: str
    sender_name: str
    sender_email: str
    idempotency_key: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    status: str  # "sent" | "failed"
    provider_id: str | None
    error: str | None = None
    simulated: bool = True


class ChannelAdapter(Protocol):
    channel: str
    name: str
    dry_run: bool

    def send(self, message: ChannelMessage) -> SendResult: ...


def unsubscribe_headers(unsubscribe_url: str) -> dict[str, str]:
    """RFC 8058 one-click unsubscribe headers, so mail clients can offer a native 'unsubscribe' button."""
    return {"List-Unsubscribe": f"<{unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def find_unsubscribe_url(body: str) -> str | None:
    match = _UNSUBSCRIBE_URL.search(body)
    return match.group(0).rstrip(".,)") if match else None


class DryRunEmailAdapter:
    """Accepts a well-formed message and pretends to send it. Nothing leaves the process."""

    channel = "email"
    name = "dry_run_email"
    dry_run = True

    def send(self, message: ChannelMessage) -> SendResult:
        if normalize_email(message.to) is None:
            return SendResult("failed", None, "invalid recipient address")
        if not message.subject.strip() or not message.body.strip():
            return SendResult("failed", None, "empty subject or body")
        if "List-Unsubscribe" not in message.headers:
            return SendResult("failed", None, "missing List-Unsubscribe header")
        digest = hashlib.sha256(message.idempotency_key.encode()).hexdigest()[:16]
        return SendResult("sent", f"dryrun-{digest}")


class LiveSendingNotAvailable(RuntimeError):
    """Live sending was requested but no real adapter is implemented: refuse instead of falling back silently."""


def select_adapter(channel: str, *, live_sending_enabled: bool) -> ChannelAdapter:
    if channel != "email":
        raise LiveSendingNotAvailable(f"channel '{channel}' has no adapter")
    if live_sending_enabled:
        raise LiveSendingNotAvailable(
            "FEATURE_LIVE_SENDING is on but no real email adapter is implemented: refusing to send"
        )
    return DryRunEmailAdapter()
