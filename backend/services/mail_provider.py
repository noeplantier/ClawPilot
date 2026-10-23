"""The one place the legacy send paths (single send, batch, campaign step, Celery tasks, tests) reach a real provider.

Never a pretend success: when nothing is configured the answer is `failed` and says what to configure.

    e-mail    SMTP (the real channel: needs FEATURE_LIVE_SENDING and SMTP_*, recipients limited to the sandbox allowlist
              while OUTREACH_SANDBOX is on) → else SendGrid (SENDGRID_API_KEY + SENDGRID_FROM_EMAIL) → else refused
    WhatsApp  Twilio (account SID starting with AC + token; recipients limited to OUTREACH_LIVE_PHONES while the sandbox
              is on) → else refused

`OUTREACH_TEST_SINK=true` replaces the providers by an in-process recorder, for automated tests only (see
`feature_flags.test_sink`): the message is not sent anywhere and its id says so (`sink:`). Never on in production.

Every caller must go through `send_gate.check(..., provider=True)` first (a test enforces it).
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from services import feature_flags, sendgrid_svc, smtp_svc, twilio_svc
from services.outreach_os import channels
from services.outreach_os.drafts import SenderIdentity

logger = logging.getLogger(__name__)

NOT_CONFIGURED = {
    "email": "No e-mail provider is configured: set SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD (with "
    "FEATURE_LIVE_SENDING=true), or SENDGRID_API_KEY and SENDGRID_FROM_EMAIL. Nothing was sent.",
    "whatsapp": "No WhatsApp provider is configured: set TWILIO_ACCOUNT_SID (starting with AC), TWILIO_AUTH_TOKEN and "
    "TWILIO_WHATSAPP_FROM. Nothing was sent.",
}


def email_provider() -> Optional[str]:
    """Which provider an e-mail would go through right now: "sink", "smtp", "sendgrid" or None."""
    if feature_flags.test_sink():
        return "sink"
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
    """Returns {status, provider_id, error}; `status` is "sent" or "failed"."""
    if feature_flags.kill_switch():
        return {"status": "failed", "provider_id": None, "error": "sending halted by the kill switch"}
    provider = email_provider()
    if provider == "sink":
        return {"status": "sent", "provider_id": f"sink:{uuid.uuid4().hex[:12]}", "error": None}
    if provider == "smtp":
        return _send_smtp(to_email, subject, body, headers or {})
    if provider == "sendgrid":
        return sendgrid_svc.send_email(to_email, subject, body, from_email=from_email, headers=headers)
    return {"status": "failed", "provider_id": None, "error": NOT_CONFIGURED["email"]}


def _send_smtp(to_email: str, subject: str, body: str, headers: dict[str, str]) -> dict:
    sender = SenderIdentity.from_env()
    adapter = smtp_svc.adapter_from_env()
    if sender is None or adapter is None:
        return {
            "status": "failed",
            "provider_id": None,
            "error": "Sender identity (OUTREACH_SENDER_*) or SMTP settings are incomplete: nothing was sent",
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
        return {"status": "sent", "provider_id": result.provider_id, "error": None}
    # "unknown" (connection lost after the message was handed over) is reported as a failure that is never retried here
    error = result.error or "the SMTP server did not accept the message"
    return {"status": "failed", "provider_id": None, "error": error}


def send_whatsapp(to_number: str, body: str) -> dict:
    """Returns {status, provider_id, error}; `status` is "sent" or "failed"."""
    if feature_flags.kill_switch():
        return {"status": "failed", "provider_id": None, "error": "sending halted by the kill switch"}
    if whatsapp_provider() == "sink":
        return {"status": "sent", "provider_id": f"sink:{uuid.uuid4().hex[:12]}", "error": None}
    return twilio_svc.send_whatsapp(to_number, body)
