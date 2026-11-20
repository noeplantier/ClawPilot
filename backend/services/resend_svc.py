"""Resend e-mail adapter: the HTTP API (port 443), the real channel behind `ChannelAdapter` where outbound SMTP ports
are closed (a free Render instance blocks 25, 465 and 587). Chosen first when its key is set (see mail_provider).

Without `RESEND_API_KEY`, `adapter_from_env()` returns None and the caller falls back to Brevo, then SMTP, or refuses
(fail closed); dispatch only uses a real adapter while `FEATURE_LIVE_SENDING` is on. The same rules as `smtp_svc` and
`brevo_svc`:

- One recipient per message, plain text, the List-Unsubscribe headers carried as they are.
- The key is never logged, returned, or part of `repr`; a provider's body is never echoed (it can repeat the request).
- A refusal (HTTP 4xx/5xx) is `failed`. A network error after the request was sent, where we cannot know whether Resend
  accepted the message, is `unknown`: the caller keeps the message in `sending` and never retries it by itself.
- While the sandbox is on, any recipient outside the allowlist is refused here too (dispatch checks first).

    RESEND_API_KEY   required (Resend > API Keys); the sender is OUTREACH_SENDER_*, on a domain verified in Resend

Resend's own limits (the free plan's daily cap) and terms apply: a quota left is not an authorization to send.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests

from services import feature_flags
from services.outreach_os import sandbox
from services.outreach_os.channels import AUTH_FAILED, ChannelMessage, SendResult
from services.outreach_os.normalize import normalize_email

logger = logging.getLogger(__name__)

API_ROOT = "https://api.resend.com"
HOST = "api.resend.com"
TIMEOUT = (5, 20)  # connect, read (seconds)


@dataclass(frozen=True)
class ResendConfig:
    api_key: str = field(repr=False)

    @classmethod
    def from_env(cls) -> Optional["ResendConfig"]:
        key = os.environ.get("RESEND_API_KEY", "").strip()
        return cls(key) if key else None


def is_configured() -> bool:
    return ResendConfig.from_env() is not None


def payload_for(message: ChannelMessage, recipient: str) -> dict[str, Any]:
    """The JSON Resend receives: one recipient, plain text, the unsubscribe headers. Pure."""
    sender = normalize_email(message.sender_email) or ""
    name = re.sub(r"[<>\"\r\n]", "", message.sender_name or "").strip()  # « Name <address> », as Resend documents it
    return {
        "from": f"{name} <{sender}>" if name else sender,
        "to": [recipient],
        "reply_to": sender,
        "subject": message.subject,
        "text": message.body,
        "headers": dict(message.headers),
    }


class ResendEmailAdapter:
    """Sends one message through Resend's API. Implements `ChannelAdapter`."""

    channel = "email"
    name = "resend"
    dry_run = False

    def __init__(
        self,
        config: ResendConfig,
        allowlist: Optional[tuple[str, ...]] = None,
        post: Callable[..., Any] = requests.post,
    ) -> None:
        self._config = config
        self._allowlist = allowlist  # None = sandbox off; a tuple (possibly empty) = only these recipients
        self._post = post

    def send(self, message: ChannelMessage) -> SendResult:
        recipient = normalize_email(message.to)
        if recipient is None or "," in message.to:
            return SendResult("failed", None, "invalid recipient address (one recipient per message)", simulated=False)
        if self._allowlist is not None and not sandbox.is_allowed(recipient, self._allowlist):
            return SendResult("failed", None, "recipient is not on the sandbox allowlist", simulated=False)
        if not message.subject.strip() or not message.body.strip():
            return SendResult("failed", None, "empty subject or body", simulated=False)
        if "List-Unsubscribe" not in message.headers:
            return SendResult("failed", None, "missing List-Unsubscribe header", simulated=False)
        if not normalize_email(message.sender_email):
            return SendResult("failed", None, "the sender address (OUTREACH_SENDER_*) is not valid", simulated=False)
        try:
            response = self._post(
                f"{API_ROOT}/emails",
                headers={"Authorization": f"Bearer {self._config.api_key}", "Content-Type": "application/json"},
                json=payload_for(message, recipient),
                timeout=TIMEOUT,
                allow_redirects=False,
            )
        except requests.ConnectTimeout:
            return SendResult("failed", None, "Resend could not be reached (timeout before sending)", simulated=False)
        except requests.ConnectionError as exc:
            if _before_sending(exc):
                return SendResult("failed", None, "Resend could not be reached", simulated=False)
            return SendResult("unknown", None, "the connection to Resend was lost while sending", simulated=False)
        except requests.Timeout:  # the request left; Resend may have accepted it
            return SendResult(
                "unknown", None, "Resend did not answer in time after the message was sent", simulated=False
            )
        except requests.RequestException as exc:
            return SendResult("failed", None, f"Resend request failed ({type(exc).__name__})", simulated=False)
        code = int(response.status_code)
        if code in (200, 201, 202):
            try:
                message_id = str((response.json() or {}).get("id") or "") or None
            except ValueError:
                message_id = None
            return SendResult("sent", message_id, None, simulated=False)
        # Only the status is used: Resend's body can echo the request (the recipient, the text).
        logger.warning("Resend answered HTTP %s", code)
        return SendResult("failed", None, explain(code), simulated=False)


def _before_sending(exc: requests.ConnectionError) -> bool:
    """True when the connection never opened (DNS, refused): nothing can have reached Resend."""
    text = repr(exc)
    return any(word in text for word in ("NameResolution", "Failed to establish", "ConnectionRefused"))


def explain(code: int) -> str:
    if code in (401, 403):
        return (
            f"{AUTH_FAILED} (Resend HTTP {code}): Resend rejected the key or the sender: check RESEND_API_KEY and that "
            "the sender's domain is verified in Resend"
        )
    if code == 422:
        return "Resend refused the message (HTTP 422): the sender's domain may not be verified, or a field is invalid"
    if code == 429:
        return "Resend's sending limit is reached (HTTP 429: rate or daily quota): try again later"
    if code >= 500:
        return f"Resend is failing on its side (HTTP {code}): nothing was resent"
    return f"Resend answered HTTP {code}"


def adapter_from_env(extra_allowed: tuple[str, ...] = ()) -> Optional[ResendEmailAdapter]:
    """The configured adapter, or None. While the sandbox is on it only writes to the allowlist (+ `extra_allowed`)."""
    config = ResendConfig.from_env()
    if config is None:
        return None
    return ResendEmailAdapter(
        config, (*feature_flags.live_allowlist(), *extra_allowed) if feature_flags.sandbox() else None
    )
