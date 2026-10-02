"""Twilio WhatsApp wrapper with graceful mock fallback."""

import logging
import os

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
    if not to_number.startswith("+"):
        to_number = "+" + to_number.lstrip("+")
    to_wa = f"whatsapp:{to_number}"

    if not is_configured():
        return {
            "status": "mock",
            "provider_id": None,
            "error": "twilio account sid not provided (SK key detected — need AC account sid)",
        }

    try:
        from twilio.rest import Client

        client = Client(SID, TOKEN)
        msg = client.messages.create(from_=FROM, to=to_wa, body=body)
        return {"status": "sent", "provider_id": msg.sid, "error": None}
    except Exception as e:
        logger.warning("twilio send failed: %s", e)
        return {"status": "mock", "provider_id": None, "error": str(e)}
