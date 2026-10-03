"""Settings — integration status, computed from the real configuration of this server (nothing hard-coded)."""

import os

from fastapi import APIRouter, Depends

from deps import get_current_user
from models import AIStatus, IntegrationSettings, OutreachStatus, WebhookStatus
from services import ai_svc, feature_flags, imap_svc, sendgrid_svc, smtp_svc, twilio_svc
from services.outreach_os.drafts import SenderIdentity

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/integrations", response_model=IntegrationSettings)
async def integrations(user: dict = Depends(get_current_user)):
    sender = SenderIdentity.from_env()
    smtp = smtp_svc.status()
    imap = imap_svc.status()
    return IntegrationSettings(
        sendgrid_from_email=os.environ.get("SENDGRID_FROM_EMAIL") or None,
        twilio_whatsapp_from=os.environ.get("TWILIO_WHATSAPP_FROM") or None,
        twilio_account_sid_configured=twilio_svc.is_configured(),
        sendgrid_configured=sendgrid_svc.is_configured(),
        ai=AIStatus(**ai_svc.status()),
        outreach=OutreachStatus(
            dry_run=feature_flags.dry_run(),
            live_sending_flag=feature_flags.is_enabled("live_sending"),
            kill_switch=feature_flags.kill_switch(),
            sender_configured=sender is not None,
            sender_email=sender.reply_to if sender else None,
            smtp_configured=smtp["configured"],
            smtp_host=smtp["host"],
            imap_configured=imap["configured"],
            imap_host=imap["host"],
            sandbox=feature_flags.sandbox(),
            allowlist_size=len(feature_flags.live_allowlist()),
        ),
        webhooks=WebhookStatus(
            production=os.environ.get("APP_ENV", "").lower() == "production",
            twilio_signature_ready=bool(twilio_svc.TOKEN),
            twilio_webhook_url_set=bool(os.environ.get("TWILIO_WEBHOOK_URL")),
            sendgrid_signature_ready=bool(sendgrid_svc.WEBHOOK_PUBLIC_KEY),
        ),
    )
