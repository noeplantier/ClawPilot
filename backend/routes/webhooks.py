"""Webhook endpoints for SendGrid and Twilio — public (no JWT).

Every inbound call is logged to `webhook_events` first (fast, durable receipt)
before any processing — see repositories/outreach_repo.py. Processing updates
the matching `email_sends`/`whatsapp_sends` row and records an `outreach_events`
entry, replacing the legacy polymorphic `messages` Mongo collection.
"""

import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from repositories import activity_repo, campaign_repo, consent_repo, lead_repo, outreach_repo
from services import sendgrid_svc, twilio_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# Map provider event type → internal send status + campaign counter field
SENDGRID_EVENT_MAP = {
    "delivered": ("delivered", None),
    "open": ("opened", "opened"),
    "click": ("opened", "opened"),  # click implies opened
    "bounce": ("failed", None),
    "dropped": ("failed", None),
    "deferred": ("queued", None),
    "spamreport": ("failed", None),
    "unsubscribe": ("failed", None),
}

# Compliance requires immediate opt-out on request — checked as a whole-word,
# case-insensitive match against the inbound message body (English + French,
# matching the primary languages seen in this codebase's demo data).
WHATSAPP_OPT_OUT_KEYWORDS = {"stop", "unsubscribe", "arret", "arrêt", "cancel", "desabonner", "désabonner"}


def _is_opt_out_message(body: str) -> bool:
    return body.strip().strip(".!?").lower() in WHATSAPP_OPT_OUT_KEYWORDS


def _reject_or_warn_unverifiable(provider: str, setting: str) -> None:
    """No verification secret configured: refuse in production, tolerate in local mock mode."""
    if os.environ.get("APP_ENV", "").lower() == "production":
        logger.error("%s webhook rejected: %s is not set in production", provider, setting)
        raise HTTPException(status_code=403, detail="Webhook signature cannot be verified")
    logger.warning("%s webhook accepted UNSIGNED: %s unset (non-production mock mode)", provider, setting)


async def require_sendgrid_signature(request: Request) -> None:
    """Reject SendGrid event webhooks without a valid ECDSA signature (fails closed, like Twilio's).

    Forged events could mark mail as bounced/unsubscribed or fake opens. Needs
    SENDGRID_WEBHOOK_PUBLIC_KEY; the signature covers the raw body, so it is read unparsed.
    """
    if not sendgrid_svc.WEBHOOK_PUBLIC_KEY:
        return _reject_or_warn_unverifiable("sendgrid", "SENDGRID_WEBHOOK_PUBLIC_KEY")
    ok = sendgrid_svc.verify_event_signature(
        await request.body(),
        request.headers.get("X-Twilio-Email-Event-Webhook-Signature"),
        request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp"),
    )
    if not ok:
        logger.warning("sendgrid webhook rejected: invalid or missing signature")
        raise HTTPException(status_code=403, detail="Invalid signature")


@router.post("/sendgrid", dependencies=[Depends(require_sendgrid_signature)])
async def sendgrid_webhook(request: Request, session: AsyncSession = Depends(get_db_session)):
    """Handle SendGrid event webhook. Body is a JSON array of events.

    Configure in SendGrid: Settings → Mail Settings → Event Webhook → POST URL = /api/webhooks/sendgrid
    """
    try:
        events: List[dict] = await request.json()
    except Exception as e:
        return {"ok": False, "error": f"invalid json: {e}"}

    if not isinstance(events, list):
        events = [events]

    processed = 0
    for ev in events:
        sg_msg_id = ev.get("sg_message_id") or ev.get("smtp-id")
        event_type = ev.get("event")
        webhook_log = await outreach_repo.log_webhook_event(session, "sendgrid", event_type, ev)

        if not sg_msg_id or not event_type:
            await outreach_repo.mark_webhook_processed(session, webhook_log, error="missing sg_message_id or event")
            continue

        status_map = SENDGRID_EVENT_MAP.get(event_type)
        if not status_map:
            await outreach_repo.mark_webhook_processed(session, webhook_log, error=f"unhandled event type {event_type}")
            continue
        new_status, counter_field = status_map

        send = await outreach_repo.upgrade_email_status_by_provider_id(session, sg_msg_id)
        if not send:
            await outreach_repo.mark_webhook_processed(session, webhook_log, error="no matching email_send")
            continue

        # Only upgrade status (sent → delivered → opened → replied)
        if outreach_repo.status_rank(new_status) <= outreach_repo.status_rank(send.status) and new_status != "failed":
            await outreach_repo.mark_webhook_processed(session, webhook_log)
            processed += 1
            continue

        send.status = new_status

        # counter_field is only ever "opened" in SENDGRID_EVENT_MAP today.
        if counter_field == "opened" and send.campaign_id:
            await campaign_repo.increment_counters(session, send.account_id, str(send.campaign_id), opened=1)

        if event_type == "unsubscribe":
            contact_id = await consent_repo.get_contact_id_by_email(session, send.account_id, send.to_email)
            if contact_id:
                await consent_repo.record_consent(
                    session,
                    send.account_id,
                    contact_id,
                    channel="email",
                    status="opted_out",
                    source="sendgrid_unsubscribe_webhook",
                    evidence={"sg_message_id": sg_msg_id},
                )

        lead_id = await consent_repo.get_lead_id_by_contact(session, send.contact_id) if send.contact_id else None
        await outreach_repo.record_outreach_event(
            session,
            send.account_id,
            channel="email",
            event_type=new_status,
            campaign_id=str(send.campaign_id) if send.campaign_id else None,
            lead_id=str(lead_id) if lead_id else None,
            meta={"provider_event": event_type, "to": send.to_email},
        )
        await outreach_repo.mark_webhook_processed(session, webhook_log)
        processed += 1

    return {"ok": True, "processed": processed, "total": len(events)}


async def require_twilio_signature(request: Request) -> None:
    """Reject Twilio webhooks that do not carry a valid `X-Twilio-Signature`.

    Inbound messages and STOP replies change consent state, so an unauthenticated caller
    must never reach the handler. Fails closed:
    - auth token set        → signature must verify (403 otherwise);
    - token unset, production → 403 (nothing to verify against);
    - token unset, non-production → allowed, for local mock mode only.

    Behind a proxy the URL the app sees can differ from the one Twilio signed, so set
    TWILIO_WEBHOOK_URL to the exact public URL configured in the Twilio console.
    """
    if not twilio_svc.TOKEN:
        return _reject_or_warn_unverifiable("twilio", "TWILIO_AUTH_TOKEN")

    form = await request.form()
    params = {k: v for k, v in form.items() if isinstance(v, str)}
    url = os.environ.get("TWILIO_WEBHOOK_URL") or str(request.url)
    if not twilio_svc.verify_signature(url, params, request.headers.get("X-Twilio-Signature")):
        logger.warning("twilio webhook rejected: invalid or missing signature (url=%s)", url)
        raise HTTPException(status_code=403, detail="Invalid signature")


@router.post("/twilio", dependencies=[Depends(require_twilio_signature)])
async def twilio_webhook(request: Request, session: AsyncSession = Depends(get_db_session)):
    """Handle Twilio message status callbacks AND inbound WhatsApp messages.

    Configure in Twilio: Messaging -> WhatsApp Sandbox (or Number) ->
    'WHEN A MESSAGE COMES IN' + 'STATUS CALLBACK' -> POST URL = /api/webhooks/twilio
    Twilio sends form-encoded data (not JSON).
    """
    form = await request.form()
    # Twilio webhooks are always form-encoded text fields, never file uploads.
    data: dict[str, str] = {k: v for k, v in form.items() if isinstance(v, str)}
    webhook_log = await outreach_repo.log_webhook_event(session, "twilio", None, data)

    message_sid = data.get("MessageSid") or data.get("SmsSid")
    message_status = data.get("MessageStatus") or data.get("SmsStatus")

    # --- Inbound message (user replied) ---
    incoming_body = data.get("Body")
    from_ = (data.get("From") or "").replace("whatsapp:", "")
    if incoming_body and from_:
        # Find lead by phone (leads live in Postgres — see repositories/lead_repo.py)
        lead = await lead_repo.get_lead_by_phone(session, from_)
        org_id = lead.get("org_id") if lead else None
        account_id = uuid.UUID(org_id) if org_id else None

        await outreach_repo.create_whatsapp_send(
            session,
            account_id,
            direction="inbound",
            from_number=from_,
            to_number=data.get("To", "").replace("whatsapp:", ""),
            body=incoming_body,
            status="replied",
            provider_message_sid=message_sid,
        )

        if account_id:
            await outreach_repo.record_outreach_event(
                session,
                account_id,
                channel="whatsapp",
                event_type="replied",
                direction="inbound",
                lead_id=lead.get("id") if lead else None,
                meta={"from": from_, "body": incoming_body[:200]},
            )
            await activity_repo.record(
                session,
                account_id,
                "whatsapp.inbound",
                f"📩 Reply from {from_}: {incoming_body[:80]}",
                {"lead_id": lead.get("id") if lead else None},
            )
            # Bump the most recent campaign's replied counter if we have lead linkage
            if lead:
                messages = await outreach_repo.list_messages(session, account_id, channel="whatsapp", limit=200)
                last_out = next((m for m in messages if m["direction"] == "outbound" and m.get("campaign_id")), None)
                if last_out:
                    await campaign_repo.increment_counters(session, account_id, last_out["campaign_id"], replied=1)

            # Immediate opt-out on request (STOP/UNSUBSCRIBE/etc.) — compliance
            # requirement, takes priority over any campaign bookkeeping above.
            if lead and lead.get("contact_id") and _is_opt_out_message(incoming_body):
                await consent_repo.record_consent(
                    session,
                    account_id,
                    uuid.UUID(lead["contact_id"]),
                    channel="whatsapp",
                    status="opted_out",
                    source="whatsapp_stop_keyword",
                    evidence={"message_sid": message_sid, "body": incoming_body},
                )

        await outreach_repo.mark_webhook_processed(session, webhook_log)
        return {"ok": True, "kind": "inbound"}

    # --- Delivery status callback ---
    if message_sid and message_status:
        status_map = {
            "queued": "queued",
            "sending": "queued",
            "sent": "sent",
            "delivered": "delivered",
            "read": "opened",
            "failed": "failed",
            "undelivered": "failed",
        }
        new_status = status_map.get(message_status, "sent")
        send = await outreach_repo.upgrade_whatsapp_status_by_sid(session, message_sid)
        if send:
            send.status = new_status
            # account_id is only ever null for inbound sends that never resolved
            # a lead; outbound sends (the ones getting a status callback) always
            # have it set at creation time in routes/messages.py.
            if send.account_id:
                if new_status == "opened" and send.campaign_id:
                    await campaign_repo.increment_counters(session, send.account_id, str(send.campaign_id), opened=1)
                lead_id = (
                    await consent_repo.get_lead_id_by_contact(session, send.contact_id) if send.contact_id else None
                )
                await outreach_repo.record_outreach_event(
                    session,
                    send.account_id,
                    channel="whatsapp",
                    event_type=new_status,
                    campaign_id=str(send.campaign_id) if send.campaign_id else None,
                    lead_id=str(lead_id) if lead_id else None,
                )
            await outreach_repo.mark_webhook_processed(session, webhook_log)
            return {"ok": True, "kind": "status", "new_status": new_status}

    await outreach_repo.mark_webhook_processed(session, webhook_log, error="noop: no matching handler")
    return {"ok": True, "kind": "noop"}
