"""SendGrid email sending wrapper with graceful mock fallback."""

import logging
import os

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL") or "noreply@clawpilot.io"


def is_configured() -> bool:
    return bool(API_KEY and FROM_EMAIL and "@" in FROM_EMAIL)


def send_email(to_email: str, subject: str, body: str, from_email: str | None = None) -> dict:
    """Send email. Returns {status, provider_id, error}.

    If SendGrid isn't fully configured (missing verified sender), returns mocked dispatch.
    """
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
