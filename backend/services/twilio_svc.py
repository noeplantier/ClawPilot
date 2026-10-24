"""Twilio WhatsApp sender. Without credentials nothing is attempted and the answer says so (no pretend dispatch)."""

import logging
import os

from services import feature_flags
from services.outreach_os.normalize import normalize_phone

logger = logging.getLogger(__name__)

SID = os.environ.get("TWILIO_ACCOUNT_SID")
TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM = os.environ.get("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886"


def verify_signature(url: str, params: dict[str, str], signature: str | None, token: str | None = None) -> bool:
    """Check Twilio's `X-Twilio-Signature` (HMAC-SHA1 of the full URL + sorted POST params).

    `token` defaults to the configured auth token. Returns False for a missing token or
    signature — callers decide whether an unconfigured deployment may skip verification.
    """
    token = TOKEN if token is None else token
    if not token or not signature:
        return False
    from twilio.request_validator import RequestValidator

    return RequestValidator(token).validate(url, params, signature)


def is_configured() -> bool:
    # Only Account SIDs that start with AC can send via Twilio REST API directly.
    return bool(SID and TOKEN and SID.startswith("AC"))


def send_whatsapp(to_number: str, body: str) -> dict:
    """Send one WhatsApp message. Returns {status, provider_id, error}; `status` is "sent" or "failed", never a pretend
    success. While the sandbox is on, only numbers in OUTREACH_LIVE_PHONES can receive a real message."""
    if feature_flags.kill_switch():
        return {"status": "failed", "provider_id": None, "error": "sending halted by the kill switch"}
    to_number = normalize_phone(to_number) or ("+" + to_number.lstrip("+"))
    if feature_flags.sandbox() and to_number not in feature_flags.live_phones():
        return {
            "status": "failed",
            "provider_id": None,
            "error": "sandbox: this number is not in OUTREACH_LIVE_PHONES, so nothing was sent",
        }
    if not is_configured():
        return {
            "status": "failed",
            "provider_id": None,
            "error": "Twilio is not configured (an account SID starting with AC, TWILIO_AUTH_TOKEN): nothing was sent",
        }

    try:
        from twilio.rest import Client

        client = Client(SID, TOKEN)
        msg = client.messages.create(from_=FROM, to=f"whatsapp:{to_number}", body=body)
        return {"status": "sent", "provider_id": msg.sid, "error": None}
    except Exception as e:
        logger.warning("twilio send failed: %s", type(e).__name__)
        return {"status": "failed", "provider_id": None, "error": f"Twilio refused the message: {str(e)[:200]}"}
