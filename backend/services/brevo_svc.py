"""Brevo e-mail adapter: the transactional HTTP API (port 443), the real channel behind `ChannelAdapter` where outbound
SMTP ports are closed (a free Render instance blocks 25, 465 and 587).

Without `BREVO_API_KEY`, `adapter_from_env()` returns None and the caller falls back to SMTP or refuses (fail closed);
dispatch only uses a real adapter while `FEATURE_LIVE_SENDING` is on. The same rules as `smtp_svc`:

- One recipient per message, plain text, the List-Unsubscribe headers carried as they are.
- The key is never logged, returned, or part of `repr`; a provider's body is never echoed (it can repeat the request).
- A refusal (HTTP 4xx/5xx) is `failed`. A network error after the request was sent, where we cannot know whether Brevo
  accepted the message, is `unknown`: the caller keeps the message in `sending` and never retries it by itself.
- While the sandbox is on, any recipient outside the allowlist is refused here too (dispatch checks first).

    BREVO_API_KEY    required (Brevo > SMTP & API > API keys); the sender is OUTREACH_SENDER_*, verified in Brevo
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests

from services import feature_flags
from services.outreach_os import sandbox
from services.outreach_os.channels import ChannelMessage, SendResult
from services.outreach_os.normalize import normalize_email

logger = logging.getLogger(__name__)

API_ROOT = "https://api.brevo.com/v3"
TIMEOUT = (5, 20)  # connect, read (seconds)


@dataclass(frozen=True)
class BrevoConfig:
    api_key: str = field(repr=False)

    @classmethod
    def from_env(cls) -> Optional["BrevoConfig"]:
        key = os.environ.get("BREVO_API_KEY", "").strip()
        return cls(key) if key else None


def is_configured() -> bool:
    return BrevoConfig.from_env() is not None


def payload_for(message: ChannelMessage, recipient: str) -> dict[str, Any]:
    """The JSON Brevo receives: one recipient, plain text, the unsubscribe headers. Pure."""
    return {
        "sender": {"name": message.sender_name, "email": normalize_email(message.sender_email) or ""},
        "to": [{"email": recipient}],
        "replyTo": {"email": normalize_email(message.sender_email) or ""},
        "subject": message.subject,
        "textContent": message.body,
        "headers": dict(message.headers),
    }


class BrevoEmailAdapter:
    """Sends one message through Brevo's transactional API. Implements `ChannelAdapter`."""

    channel = "email"
    name = "brevo"
    dry_run = False

    def __init__(
        self,
        config: BrevoConfig,
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
                f"{API_ROOT}/smtp/email",
                headers={"api-key": self._config.api_key, "accept": "application/json"},
                json=payload_for(message, recipient),
                timeout=TIMEOUT,
                allow_redirects=False,
            )
        except requests.ConnectTimeout:
            return SendResult("failed", None, "Brevo could not be reached (timeout before sending)", simulated=False)
        except requests.ConnectionError as exc:
            if _before_sending(exc):
                return SendResult("failed", None, "Brevo could not be reached", simulated=False)
            return SendResult("unknown", None, "the connection to Brevo was lost while sending", simulated=False)
        except requests.Timeout:  # the request left; Brevo may have accepted it
            return SendResult(
                "unknown", None, "Brevo did not answer in time after the message was sent", simulated=False
            )
        except requests.RequestException as exc:
            return SendResult("failed", None, f"Brevo request failed ({type(exc).__name__})", simulated=False)
        code = int(response.status_code)
        if code in (200, 201, 202):
            try:
                message_id = str((response.json() or {}).get("messageId") or "") or None
            except ValueError:
                message_id = None
            return SendResult("sent", message_id, None, simulated=False)
        # Only the status is used: Brevo's body can echo the request (the recipient, the text).
        logger.warning("Brevo answered HTTP %s", code)
        return SendResult("failed", None, explain(code), simulated=False)


def _before_sending(exc: requests.ConnectionError) -> bool:
    """True when the connection never opened (DNS, refused): nothing can have reached Brevo."""
    text = repr(exc)
    return any(word in text for word in ("NameResolution", "Failed to establish", "ConnectionRefused"))


def explain(code: int) -> str:
    if code in (401, 403):
        return (
            f"Brevo rejected the key or the sender (HTTP {code}): check BREVO_API_KEY and the sender verified in Brevo"
        )
    if code == 400:
        return "Brevo refused the message (HTTP 400): the sender may not be verified in Brevo, or a field is invalid"
    if code == 402:
        return "Brevo refused the message (HTTP 402): the plan or its daily quota does not allow it"
    if code == 429:
        return "Brevo's sending limit is reached (HTTP 429): try again later"
    if code >= 500:
        return f"Brevo is failing on its side (HTTP {code}): nothing was resent"
    return f"Brevo answered HTTP {code}"


def adapter_from_env(extra_allowed: tuple[str, ...] = ()) -> Optional[BrevoEmailAdapter]:
    """The configured adapter, or None. While the sandbox is on it only writes to the allowlist (+ `extra_allowed`)."""
    config = BrevoConfig.from_env()
    if config is None:
        return None
    return BrevoEmailAdapter(
        config, (*feature_flags.live_allowlist(), *extra_allowed) if feature_flags.sandbox() else None
    )
