"""The one place the legacy send paths (single send, batch, campaign step, Celery tasks, tests) reach a real provider.

Never a pretend success: when nothing is configured the answer is `failed` and says what to configure.

    e-mail    Brevo's HTTP API (BREVO_API_KEY, port 443: works where SMTP ports are closed) → else SMTP (SMTP_*);
              both real channels need FEATURE_LIVE_SENDING, recipients limited to the sandbox allowlist while
              OUTREACH_SANDBOX is on → else SendGrid (SENDGRID_API_KEY + SENDGRID_FROM_EMAIL) → else refused
    WhatsApp  Twilio (account SID starting with AC + token; recipients limited to OUTREACH_LIVE_PHONES while the sandbox
              is on) → else refused

`OUTREACH_TEST_SINK=true` replaces the providers by an in-process recorder, for automated tests only (see
`feature_flags.test_sink`): the message is not sent anywhere and its id says so (`sink:`). Never on in production.

Every caller must go through `send_gate.check(..., provider=True)` first (a test enforces it).
"""

from __future__ import annotations

import logging
import socket
import time
import uuid
from typing import Any, Callable, Optional

from services import brevo_svc, feature_flags, sendgrid_svc, smtp_svc, twilio_svc
from services.outreach_os import channels
from services.outreach_os.drafts import SenderIdentity

logger = logging.getLogger(__name__)

NOT_CONFIGURED = {
    "email": "No e-mail provider is configured: set BREVO_API_KEY, or SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD (with "
    "FEATURE_LIVE_SENDING=true), or SENDGRID_API_KEY and SENDGRID_FROM_EMAIL. Nothing was sent.",
    "whatsapp": "No WhatsApp provider is configured: set TWILIO_ACCOUNT_SID (starting with AC), TWILIO_AUTH_TOKEN and "
    "TWILIO_WHATSAPP_FROM. Nothing was sent.",
}


def email_provider() -> Optional[str]:
    """Which provider an e-mail would go through right now: "sink", "brevo", "smtp", "sendgrid" or None."""
    if feature_flags.test_sink():
        return "sink"
    if not feature_flags.dry_run() and brevo_svc.is_configured():
        return "brevo"
    if not feature_flags.dry_run() and smtp_svc.is_configured():
        return "smtp"
    if sendgrid_svc.is_configured():
        return "sendgrid"
    return None


def whatsapp_provider() -> Optional[str]:
    if feature_flags.test_sink():
        return "sink"
    return "twilio" if twilio_svc.is_configured() else None


def provider_for(channel: str) -> Optional[str]:
    return email_provider() if channel == "email" else whatsapp_provider()


def send_email(
    to_email: str, subject: str, body: str, from_email: str | None = None, headers: dict[str, str] | None = None
) -> dict:
    """Returns {status, provider_id, error, provider, ambiguous}; `status` is "sent" or "failed".

    `provider` names who carried (or refused) the message, so a record never claims SendGrid for an SMTP send.
    `ambiguous` is True when the server may already have accepted the message (the connection dropped while sending):
    such a message is reported as failed but must never be sent again blindly."""
    if feature_flags.kill_switch():
        return {
            "status": "failed",
            "provider_id": None,
            "error": "sending halted by the kill switch",
            "provider": None,
            "ambiguous": False,
        }
    provider = email_provider()
    if provider == "sink":
        return {
            "status": "sent",
            "provider_id": f"sink:{uuid.uuid4().hex[:12]}",
            "error": None,
            "provider": "sink",
            "ambiguous": False,
        }
    if provider in ("brevo", "smtp"):
        return {**_send_live(to_email, subject, body, headers or {}), "provider": provider}
    if provider == "sendgrid":
        result = sendgrid_svc.send_email(to_email, subject, body, from_email=from_email, headers=headers)
        return {**result, "provider": "sendgrid", "ambiguous": False}
    return {
        "status": "failed",
        "provider_id": None,
        "error": NOT_CONFIGURED["email"],
        "provider": None,
        "ambiguous": False,
    }


REACH_TIMEOUT = 3.0  # seconds: opening a connection, nothing else
REACH_TTL = 600.0  # a probe is reused for 10 minutes
_reach_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}


def live_endpoint() -> Optional[tuple[str, str, int]]:
    """(provider, host, port) of the channel a real e-mail would take, in `live_adapter` order; None if none."""
    if brevo_svc.is_configured():
        return "brevo", "api.brevo.com", 443
    config = smtp_svc.SmtpConfig.from_env()
    if config is not None:
        return "smtp", config.host, config.port
    return None


def reachable(
    connect: Callable[..., Any] = socket.create_connection, clock: Callable[[], float] = time.monotonic
) -> dict[str, Any]:
    """Can this server open a connection to its e-mail channel? {ok, provider, host, port, error}.

    « Configured » is not « working »: a free Render instance closes outbound SMTP ports, so a complete SMTP setup
    can never deliver. This only opens a TCP connection (no TLS, no sign-in, nothing sent) and caches the answer
    for REACH_TTL. The in-process test recorder is always reachable."""
    if feature_flags.test_sink():
        return {"ok": True, "provider": "sink", "host": None, "port": None, "error": None}
    endpoint = live_endpoint()
    if endpoint is None:
        return {"ok": False, "provider": None, "host": None, "port": None, "error": "not_configured"}
    provider, host, port = endpoint
    cached = _reach_cache.get((host, port))
    if cached and clock() - cached[0] < REACH_TTL:
        return cached[1]
    error: Optional[str] = None
    try:
        connect((host, port), timeout=REACH_TIMEOUT).close()
    except OSError as exc:  # refused, timeout, unknown host: the class says which, never a secret
        error = type(exc).__name__
    result = {"ok": error is None, "provider": provider, "host": host, "port": port, "error": error}
    _reach_cache[(host, port)] = (clock(), result)
    return result


def live_adapter(extra_allowed: tuple[str, ...] = ()) -> Optional[channels.ChannelAdapter]:
    """The real e-mail channel for every path that sends a message: Brevo when its key is set (HTTPS, port 443), else
    SMTP, else None (the caller refuses: fail closed). The sandbox applies to both."""
    adapter: Optional[channels.ChannelAdapter] = brevo_svc.adapter_from_env(extra_allowed)
    if adapter is None:
        adapter = smtp_svc.adapter_from_env(extra_allowed)
    return adapter


def _send_live(to_email: str, subject: str, body: str, headers: dict[str, str]) -> dict:
    sender = SenderIdentity.from_env()
    adapter = live_adapter()
    if sender is None or adapter is None:
        return {
            "status": "failed",
            "provider_id": None,
            "error": "Sender identity (OUTREACH_SENDER_*) or the e-mail provider settings are incomplete: "
            "nothing was sent",
            "ambiguous": False,
        }
    message = channels.ChannelMessage(
        to=to_email,
        subject=subject,
        body=body,
        sender_name=sender.name,
        sender_email=sender.reply_to,
        idempotency_key=f"legacy:{uuid.uuid4()}",
        headers=headers,
    )
    result = adapter.send(message)
    if result.status == "sent":
        return {"status": "sent", "provider_id": result.provider_id, "error": None, "ambiguous": False}
    # "unknown" (connection lost after the message was handed over) is reported as a failure, flagged ambiguous: the
    # server may have accepted it, so no path may send it again by itself
    error = result.error or "the e-mail provider did not accept the message"
    return {"status": "failed", "provider_id": None, "error": error, "ambiguous": result.status == "unknown"}


def send_whatsapp(to_number: str, body: str) -> dict:
    """Returns {status, provider_id, error}; `status` is "sent" or "failed"."""
    if feature_flags.kill_switch():
        return {"status": "failed", "provider_id": None, "error": "sending halted by the kill switch"}
    if whatsapp_provider() == "sink":
        return {"status": "sent", "provider_id": f"sink:{uuid.uuid4().hex[:12]}", "error": None}
    return twilio_svc.send_whatsapp(to_number, body)
