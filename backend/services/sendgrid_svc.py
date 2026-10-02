"""SendGrid email sending wrapper with graceful mock fallback."""

import logging
import os

from services import feature_flags

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("SENDGRID_API_KEY")
# No default sender: a message never leaves from an address nobody configured. Without SENDGRID_FROM_EMAIL, mock.
FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL") or None


# Verification key from SendGrid: Settings → Mail Settings → Event Webhook → "Signature Verification".
WEBHOOK_PUBLIC_KEY = os.environ.get("SENDGRID_WEBHOOK_PUBLIC_KEY")


def verify_event_signature(
    raw_body: bytes, signature: str | None, timestamp: str | None, public_key: str | None = None
) -> bool:
    """Check SendGrid's ECDSA signature over `timestamp + raw body` (event webhook).

    Returns False — never raises — for a missing key/header or any malformed input.
    """
    public_key = WEBHOOK_PUBLIC_KEY if public_key is None else public_key
    if not public_key or not signature or not timestamp:
        return False
    try:
        from sendgrid.helpers.eventwebhook import EventWebhook

        return bool(EventWebhook(public_key).verify_signature(raw_body.decode("utf-8"), signature, timestamp))
    except Exception:
        return False


def is_configured() -> bool:
    return bool(API_KEY and FROM_EMAIL and "@" in FROM_EMAIL)


def send_email(to_email: str, subject: str, body: str, from_email: str | None = None) -> dict:
    """Send email. Returns {status, provider_id, error}.

    If SendGrid isn't fully configured (no API key or no `SENDGRID_FROM_EMAIL`), returns mocked dispatch.
    """
    if feature_flags.kill_switch():
        return {"status": "failed", "provider_id": None, "error": "sending halted by the kill switch"}
    sender = from_email or FROM_EMAIL
    if not API_KEY or not sender:
        return {"status": "mock", "provider_id": None, "error": "sendgrid not configured"}

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import ClickTracking, Mail, OpenTracking, TrackingSettings

        html = (
            '<div style="font-family:system-ui,-apple-system,sans-serif;line-height:1.6;color:#111">'
            + body.replace("\n", "<br/>")
            + "</div>"
        )

        message = Mail(from_email=sender, to_emails=to_email, subject=subject, html_content=html)
        ts = TrackingSettings()
        ts.click_tracking = ClickTracking(True, True)
        ts.open_tracking = OpenTracking(True)
        message.tracking_settings = ts

        sg = SendGridAPIClient(API_KEY)
        resp = sg.send(message)
        if 200 <= resp.status_code < 300:
            return {
                "status": "sent",
                "provider_id": resp.headers.get("X-Message-Id"),
                "error": None,
            }
        return {"status": "failed", "provider_id": None, "error": f"status {resp.status_code}"}
    except Exception as e:
        logger.warning("sendgrid send failed: %s", e)
        # Graceful mock on failure (e.g., unverified sender) so UX continues
        return {"status": "mock", "provider_id": None, "error": str(e)}
