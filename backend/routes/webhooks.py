"""Webhook endpoints for SendGrid and Twilio — public (no JWT)."""
import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Request
from deps import db
from services import engagement

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Map provider event type → internal Message.status + engagement event
SENDGRID_EVENT_MAP = {
    "delivered":   ("delivered", "delivered"),
    "open":        ("opened",    "opened"),
    "click":       ("opened",    "clicked"),
    "bounce":      ("failed",    "bounced"),
    "dropped":     ("failed",    "bounced"),
    "deferred":    ("queued",    None),
    "spamreport":  ("failed",    "spam"),
    "unsubscribe": ("failed",    "unsubscribed"),
}


@router.post("/sendgrid")
async def sendgrid_webhook(request: Request):
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
        if not sg_msg_id or not event_type:
            continue

        # SendGrid appends a suffix to sg_message_id; match by prefix
        base_id = sg_msg_id.split(".")[0] if sg_msg_id else None
        mapping = SENDGRID_EVENT_MAP.get(event_type)
        if not mapping:
            continue
        new_status, engagement_event = mapping

        # Find matching message by provider_id prefix or exact
        msg = await db.messages.find_one(
            {"$or": [
                {"provider_id": sg_msg_id},
                {"provider_id": {"$regex": f"^{base_id}"}} if base_id else {},
            ]},
            {"_id": 0},
        )
        if not msg:
            continue

        # Only upgrade status (sent → delivered → opened → replied)
        rank = {"queued": 0, "mock": 0, "sent": 1, "delivered": 2, "opened": 3, "replied": 4, "failed": -1}
        current_rank = rank.get(msg.get("status", "queued"), 0)
        new_rank = rank.get(new_status, 0)
        if new_rank > current_rank or new_status == "failed":
            await db.messages.update_one({"id": msg["id"]}, {"$set": {"status": new_status}})

        # Trigger engagement engine — this updates lead score/stage and bumps campaign counter
        if engagement_event and msg.get("lead_id"):
            await engagement.apply(
                db,
                msg["lead_id"],
                engagement_event,
                channel="email",
                campaign_id=msg.get("campaign_id"),
            )
            # If event is suppressive, cancel pending jobs for this lead
            if engagement_event in ("bounced", "unsubscribed", "spam"):
                await engagement.remove_from_active_campaigns(db, msg["lead_id"], msg.get("org_id"))

        processed += 1

    return {"ok": True, "processed": processed, "total": len(events)}


@router.post("/twilio")
async def twilio_webhook(request: Request):
    """Handle Twilio message status callbacks AND inbound WhatsApp messages.

    Configure in Twilio: Messaging → WhatsApp Sandbox (or Number) → 'WHEN A MESSAGE COMES IN' + 'STATUS CALLBACK' → POST URL = /api/webhooks/twilio
    Twilio sends form-encoded data (not JSON).
    """
    form = await request.form()
    data = dict(form)

    message_sid = data.get("MessageSid") or data.get("SmsSid")
    message_status = data.get("MessageStatus") or data.get("SmsStatus")

    # --- Inbound message (user replied) ---
    incoming_body = data.get("Body")
    from_ = (data.get("From") or "").replace("whatsapp:", "")
    if incoming_body and from_:
        # Find lead by phone
        lead = await db.leads.find_one({"phone": from_}, {"_id": 0})
        org_id = lead.get("org_id") if lead else None

        await db.messages.insert_one({
            "id": f"in-{message_sid or from_}"[:120],
            "org_id": org_id,
            "campaign_id": None,
            "lead_id": lead.get("id") if lead else None,
            "channel": "whatsapp",
            "direction": "inbound",
            "to": data.get("To", "").replace("whatsapp:", ""),
            "subject": None,
            "body": incoming_body,
            "status": "replied",
            "provider_id": message_sid,
            "error": None,
            "created_at": _now_iso(),
        })

        if org_id:
            await db.activity.insert_one({
                "id": f"wh-in-{message_sid or from_}"[:120],
                "org_id": org_id,
                "kind": "whatsapp.inbound",
                "title": f"📩 Reply from {from_}: {incoming_body[:80]}",
                "meta": {"lead_id": lead.get("id") if lead else None},
                "created_at": _now_iso(),
            })
            # Bump the most recent campaign's replied counter if we have lead linkage
            if lead:
                last_out = await db.messages.find_one(
                    {"lead_id": lead["id"], "direction": "outbound", "channel": "whatsapp"},
                    {"_id": 0, "campaign_id": 1},
                    sort=[("created_at", -1)],
                )
                if last_out and last_out.get("campaign_id"):
                    await db.campaigns.update_one(
                        {"id": last_out["campaign_id"], "org_id": org_id},
                        {"$inc": {"replied": 1}},
                    )

        return {"ok": True, "kind": "inbound"}

    # --- Delivery status callback ---
    if message_sid and message_status:
        status_map = {
            "queued": "queued", "sending": "queued", "sent": "sent",
            "delivered": "delivered", "read": "opened",
            "failed": "failed", "undelivered": "failed",
        }
        new_status = status_map.get(message_status, "sent")
        msg = await db.messages.find_one({"provider_id": message_sid}, {"_id": 0})
        if msg:
            await db.messages.update_one({"id": msg["id"]}, {"$set": {"status": new_status}})
            if new_status == "opened" and msg.get("campaign_id"):
                await db.campaigns.update_one(
                    {"id": msg["campaign_id"], "org_id": msg["org_id"]},
                    {"$inc": {"opened": 1}},
                )
            return {"ok": True, "kind": "status", "new_status": new_status}

    return {"ok": True, "kind": "noop"}
