"""Messaging routes — send email & whatsapp, list threads."""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from models import Message, SendEmailIn, SendWhatsAppIn, Activity
from deps import db, get_current_user
from services.sendgrid_svc import send_email
from services.twilio_svc import send_whatsapp

router = APIRouter(prefix="/messages", tags=["messages"])


class BatchSendIn(BaseModel):
    lead_ids: List[str]
    subject: Optional[str] = None
    body: str
    campaign_id: Optional[str] = None


def _render(template: str, lead: dict) -> str:
    """Simple {{var}} substitution using lead fields."""
    if not template:
        return ""
    first = (lead.get("full_name") or "").split(" ")[0] or "there"
    mapping = {
        "{{first_name}}": first,
        "{{full_name}}": lead.get("full_name") or "",
        "{{company}}": lead.get("company") or "",
        "{{title}}": lead.get("title") or "",
        "{{country}}": lead.get("country") or "",
    }
    out = template
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out


async def _log(org_id: str, kind: str, title: str):
    act = Activity(org_id=org_id, kind=kind, title=title)
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


@router.get("", response_model=List[Message])
async def list_messages(
    user: dict = Depends(get_current_user),
    channel: Optional[str] = None,
    limit: int = 200,
):
    q = {"org_id": user["org_id"]}
    if channel:
        q["channel"] = channel
    return await db.messages.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


@router.post("/email")
async def send_email_route(payload: SendEmailIn, user: dict = Depends(get_current_user)):
    result = send_email(payload.to, payload.subject, payload.body)

    msg = Message(
        org_id=user["org_id"],
        campaign_id=payload.campaign_id,
        lead_id=payload.lead_id,
        channel="email",
        to=payload.to,
        subject=payload.subject,
        body=payload.body,
        status=result["status"],
        provider_id=result.get("provider_id"),
        error=result.get("error"),
    )
    d = msg.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.messages.insert_one(d)
    await _log(user["org_id"], "message.email", f"Email {result['status']} → {payload.to}")

    if payload.campaign_id:
        await db.campaigns.update_one(
            {"id": payload.campaign_id, "org_id": user["org_id"]},
            {"$inc": {"sent": 1}},
        )
    return {"message": msg, "result": result}


@router.post("/whatsapp")
async def send_whatsapp_route(payload: SendWhatsAppIn, user: dict = Depends(get_current_user)):
    result = send_whatsapp(payload.to, payload.body)

    msg = Message(
        org_id=user["org_id"],
        campaign_id=payload.campaign_id,
        lead_id=payload.lead_id,
        channel="whatsapp",
        to=payload.to,
        body=payload.body,
        status=result["status"],
        provider_id=result.get("provider_id"),
        error=result.get("error"),
    )
    d = msg.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.messages.insert_one(d)
    await _log(user["org_id"], "message.whatsapp", f"WhatsApp {result['status']} → {payload.to}")

    if payload.campaign_id:
        await db.campaigns.update_one(
            {"id": payload.campaign_id, "org_id": user["org_id"]},
            {"$inc": {"sent": 1}},
        )
    return {"message": msg, "result": result}


@router.post("/email/batch")
async def batch_send_email(payload: BatchSendIn, user: dict = Depends(get_current_user)):
    """Send personalized emails to multiple leads in one call."""
    if not payload.subject:
        raise HTTPException(status_code=400, detail="Subject is required for email batch")

    leads = await db.leads.find(
        {"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]}, {"_id": 0}
    ).to_list(len(payload.lead_ids))

    results = []
    docs = []
    sent = 0
    mocked = 0
    failed = 0
    skipped = 0

    for lead in leads:
        if not lead.get("email"):
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": "no email"})
            continue
        subj = _render(payload.subject, lead)
        body = _render(payload.body, lead)
        result = send_email(lead["email"], subj, body)

        msg = Message(
            org_id=user["org_id"],
            campaign_id=payload.campaign_id,
            lead_id=lead["id"],
            channel="email",
            to=lead["email"],
            subject=subj,
            body=body,
            status=result["status"],
            provider_id=result.get("provider_id"),
            error=result.get("error"),
        )
        d = msg.model_dump()
        d["created_at"] = d["created_at"].isoformat()
        docs.append(d)

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1
        results.append({"lead_id": lead["id"], "email": lead["email"], "status": result["status"]})

    if docs:
        await db.messages.insert_many(docs)

    if payload.campaign_id:
        await db.campaigns.update_one(
            {"id": payload.campaign_id, "org_id": user["org_id"]},
            {"$inc": {"sent": sent + mocked}},
        )

    await _log(user["org_id"], "message.email.batch", f"Batch email · {sent} sent, {mocked} mocked, {failed} failed, {skipped} skipped")
    return {
        "dispatched": sent + mocked,
        "sent": sent,
        "mocked": mocked,
        "failed": failed,
        "skipped": skipped,
        "total": len(payload.lead_ids),
        "results": results,
    }


@router.post("/whatsapp/batch")
async def batch_send_whatsapp(payload: BatchSendIn, user: dict = Depends(get_current_user)):
    leads = await db.leads.find(
        {"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]}, {"_id": 0}
    ).to_list(len(payload.lead_ids))

    results = []
    docs = []
    sent = 0
    mocked = 0
    failed = 0
    skipped = 0

    for lead in leads:
        if not lead.get("phone"):
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": "no phone"})
            continue
        body = _render(payload.body, lead)
        result = send_whatsapp(lead["phone"], body)

        msg = Message(
            org_id=user["org_id"],
            campaign_id=payload.campaign_id,
            lead_id=lead["id"],
            channel="whatsapp",
            to=lead["phone"],
            body=body,
            status=result["status"],
            provider_id=result.get("provider_id"),
            error=result.get("error"),
        )
        d = msg.model_dump()
        d["created_at"] = d["created_at"].isoformat()
        docs.append(d)

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1
        results.append({"lead_id": lead["id"], "phone": lead["phone"], "status": result["status"]})

    if docs:
        await db.messages.insert_many(docs)

    if payload.campaign_id:
        await db.campaigns.update_one(
            {"id": payload.campaign_id, "org_id": user["org_id"]},
            {"$inc": {"sent": sent + mocked}},
        )

    await _log(user["org_id"], "message.whatsapp.batch", f"Batch WhatsApp · {sent} sent, {mocked} mocked, {failed} failed, {skipped} skipped")
    return {
        "dispatched": sent + mocked,
        "sent": sent,
        "mocked": mocked,
        "failed": failed,
        "skipped": skipped,
        "total": len(payload.lead_ids),
        "results": results,
    }
