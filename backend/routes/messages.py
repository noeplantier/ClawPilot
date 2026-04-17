"""Messaging routes — send email & whatsapp, list threads."""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from models import Message, SendEmailIn, SendWhatsAppIn, Activity
from deps import db, get_current_user
from services.sendgrid_svc import send_email
from services.twilio_svc import send_whatsapp

router = APIRouter(prefix="/messages", tags=["messages"])


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
