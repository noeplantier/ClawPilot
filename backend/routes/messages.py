"""Messaging routes — send email & whatsapp, list threads.

Postgres-backed: `email_sends`/`whatsapp_sends` (detail) + `outreach_events`
(unified timeline that real analytics timeseries are built from).
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import SendEmailIn, SendWhatsAppIn
from repositories import (
    activity_repo,
    audit_repo,
    campaign_repo,
    consent_repo,
    lead_repo,
    outreach_repo,
)
from routes._refusal import block_detail, refusal
from services import legacy_email, send_gate
from services.sendgrid_svc import send_email
from services.templating import render as _render
from services.twilio_svc import send_whatsapp

router = APIRouter(prefix="/messages", tags=["messages"])


def _event_type_for(status: str) -> str:
    return "failed" if status == "failed" else "sent"


async def _enforce_consent_for_lead(
    session: AsyncSession, account_id: uuid.UUID, lead_id: Optional[str], channel: str
) -> Optional[uuid.UUID]:
    """Raises 403 if this specific lead has not consented for `channel`. Returns
    the lead's primary contact_id (or None) so the caller can stamp it on the
    email_send/whatsapp_send row it's about to create — without this, webhook
    status updates can't attribute engagement back to a lead for scoring (see
    repositories/lead_repo.py::_gather_signals)."""
    if not lead_id:
        return None
    blocked = await lead_repo.discovery_send_block(session, account_id, uuid.UUID(lead_id))
    if blocked:
        await audit_repo.log(
            session,
            account_id,
            action="send.blocked_review",
            resource_type="lead",
            resource_id=uuid.UUID(lead_id),
            diff={"channel": channel, "reason": blocked},
        )
        await session.commit()  # get_db_session rolls back on HTTPException: persist the evidence first
        raise HTTPException(status_code=403, detail=f"Recipient cannot be contacted: {blocked}")
    contact_id = await consent_repo.get_primary_contact_id(session, uuid.UUID(lead_id))
    if not contact_id:
        return None
    status = await consent_repo.get_status(session, contact_id, channel)
    if not consent_repo.can_send(channel, status):
        await audit_repo.log(
            session,
            account_id,
            action="send.blocked_consent",
            resource_type="lead",
            resource_id=uuid.UUID(lead_id),
            diff={"channel": channel, "consent_status": status},
        )
        await session.commit()  # get_db_session rolls back on HTTPException: persist the evidence first
        raise HTTPException(status_code=403, detail=f"Recipient has not consented to {channel} outreach")
    return contact_id


async def _gate(session: AsyncSession, account_id: uuid.UUID, channel: str) -> Optional[send_gate.SendBlocked]:
    """None if one more message may go out now, else why not (batch loops stop at the first refusal)."""
    try:
        await send_gate.check(session, account_id, channel)
    except send_gate.SendBlocked as blocked:
        return blocked
    return None


async def _audit_batch_block(session: AsyncSession, user: dict, blocked: send_gate.SendBlocked, channel: str) -> None:
    await audit_repo.log(
        session,
        uuid.UUID(user["org_id"]),
        action="send.blocked_limits",
        resource_type="send",
        actor_user_id=uuid.UUID(user["id"]),
        diff={"code": blocked.code, "channel": channel, "batch": True},
    )


class BatchSendIn(BaseModel):
    lead_ids: List[str]
    subject: Optional[str] = None
    body: str
    campaign_id: Optional[str] = None


@router.get("", response_model=List[dict])
async def list_messages(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    channel: Optional[str] = None,
    lead_id: Optional[str] = None,
    limit: int = 200,
):
    return await outreach_repo.list_messages(
        session, uuid.UUID(user["org_id"]), channel=channel, lead_id=lead_id, limit=limit
    )


@router.post("/email")
async def send_email_route(
    payload: SendEmailIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    contact_id = await _enforce_consent_for_lead(session, account_id, payload.lead_id, "email")
    try:
        await send_gate.check(session, account_id, "email")
    except send_gate.SendBlocked as blocked:
        raise await refusal(session, user, blocked, resource_type="send", action="send.blocked_limits", channel="email")
    source = None
    if payload.lead_id:
        known = await lead_repo.get_leads_by_ids(session, account_id, [payload.lead_id])
        source = known[0].get("source") if known else None
    try:
        prepared = await legacy_email.prepare(
            session, account_id, to_email=payload.to, body=payload.body, lead_id=payload.lead_id, source=source
        )
    except legacy_email.EmailNotCompliant as exc:
        await audit_repo.log(
            session,
            account_id,
            action="send.blocked_compliance",
            resource_type="send",
            actor_user_id=uuid.UUID(user["id"]),
            diff={"code": exc.code, "channel": "email"},
        )
        await session.commit()  # get_db_session rolls back on HTTPException: persist the evidence first
        raise HTTPException(status_code=409 if exc.code != "recipient_unknown" else 400, detail=exc.message)
    result = send_email(payload.to, payload.subject, prepared.body, headers=prepared.headers)

    send = await outreach_repo.create_email_send(
        session,
        account_id,
        campaign_id=uuid.UUID(payload.campaign_id) if payload.campaign_id else None,
        contact_id=contact_id,
        to_email=payload.to,
        subject=payload.subject,
        body=prepared.body,
        status=result["status"],
        provider_message_id=result.get("provider_id"),
        error=result.get("error"),
    )
    await outreach_repo.record_outreach_event(
        session,
        account_id,
        channel="email",
        event_type=_event_type_for(result["status"]),
        campaign_id=payload.campaign_id,
        lead_id=payload.lead_id,
    )
    await activity_repo.record(session, user["org_id"], "message.email", f"Email {result['status']} → {payload.to}")

    if payload.campaign_id:
        await campaign_repo.increment_counters(session, account_id, payload.campaign_id, sent=1)
    lead_uuid = uuid.UUID(payload.lead_id) if payload.lead_id else None
    return {
        "message": outreach_repo.email_to_message(send, lead_uuid),
        "result": result,
    }


@router.post("/whatsapp")
async def send_whatsapp_route(
    payload: SendWhatsAppIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    contact_id = await _enforce_consent_for_lead(session, account_id, payload.lead_id, "whatsapp")
    try:
        await send_gate.check(session, account_id, "whatsapp")
    except send_gate.SendBlocked as blocked:
        raise await refusal(
            session, user, blocked, resource_type="send", action="send.blocked_limits", channel="whatsapp"
        )
    result = send_whatsapp(payload.to, payload.body)

    send = await outreach_repo.create_whatsapp_send(
        session,
        account_id,
        campaign_id=uuid.UUID(payload.campaign_id) if payload.campaign_id else None,
        contact_id=contact_id,
        direction="outbound",
        from_number="",
        to_number=payload.to,
        body=payload.body,
        status=result["status"],
        provider_message_sid=result.get("provider_id"),
        error=result.get("error"),
    )
    await outreach_repo.record_outreach_event(
        session,
        account_id,
        channel="whatsapp",
        event_type=_event_type_for(result["status"]),
        campaign_id=payload.campaign_id,
        lead_id=payload.lead_id,
    )
    await activity_repo.record(
        session,
        user["org_id"],
        "message.whatsapp",
        f"WhatsApp {result['status']} → {payload.to}",
    )

    if payload.campaign_id:
        await campaign_repo.increment_counters(session, account_id, payload.campaign_id, sent=1)
    lead_uuid = uuid.UUID(payload.lead_id) if payload.lead_id else None
    return {
        "message": outreach_repo.whatsapp_to_message(send, lead_uuid),
        "result": result,
    }


@router.post("/email/batch")
async def batch_send_email(
    payload: BatchSendIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Send personalized emails to multiple leads in one call."""
    if not payload.subject:
        raise HTTPException(status_code=400, detail="Subject is required for email batch")

    account_id = uuid.UUID(user["org_id"])
    leads = await lead_repo.get_leads_by_ids(session, account_id, payload.lead_ids)

    results = []
    sent = mocked = failed = skipped = not_attempted = 0
    blocked: Optional[send_gate.SendBlocked] = None

    for index, lead in enumerate(leads):
        if not lead.get("email"):
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": "no email"})
            continue
        if not consent_repo.can_send("email", lead["email_consent"]):
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": "opted out"})
            continue
        blocked = await _gate(session, account_id, "email")
        if blocked:  # limits, pause or kill switch: stop here, nothing further is sent
            for rest in leads[index:]:
                not_attempted += 1
                results.append({"lead_id": rest["id"], "status": "blocked", "reason": blocked.code})
            await _audit_batch_block(session, user, blocked, "email")
            break
        subj = _render(payload.subject, lead)
        try:
            prepared = await legacy_email.prepare(
                session,
                account_id,
                to_email=lead["email"],
                body=_render(payload.body, lead),
                lead_id=lead["id"],
                source=lead.get("source"),
            )
        except legacy_email.EmailNotCompliant as exc:
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": exc.code})
            continue
        body = prepared.body
        result = send_email(lead["email"], subj, body, headers=prepared.headers)

        contact_id = uuid.UUID(lead["contact_id"]) if lead.get("contact_id") else None
        await outreach_repo.create_email_send(
            session,
            account_id,
            campaign_id=uuid.UUID(payload.campaign_id) if payload.campaign_id else None,
            contact_id=contact_id,
            to_email=lead["email"],
            subject=subj,
            body=body,
            status=result["status"],
            provider_message_id=result.get("provider_id"),
            error=result.get("error"),
        )
        await outreach_repo.record_outreach_event(
            session,
            account_id,
            channel="email",
            event_type=_event_type_for(result["status"]),
            campaign_id=payload.campaign_id,
            lead_id=lead["id"],
        )

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1
        results.append({"lead_id": lead["id"], "email": lead["email"], "status": result["status"]})

    if payload.campaign_id:
        await campaign_repo.increment_counters(session, account_id, payload.campaign_id, sent=sent + mocked)

    await activity_repo.record(
        session,
        user["org_id"],
        "message.email.batch",
        f"Batch email · {sent} sent, {mocked} mocked, {failed} failed, {skipped} skipped"
        + (f", {not_attempted} not attempted ({blocked.code})" if blocked else ""),
    )
    return {
        "dispatched": sent + mocked,
        "sent": sent,
        "mocked": mocked,
        "failed": failed,
        "skipped": skipped,
        "not_attempted": not_attempted,
        "blocked": block_detail(blocked) if blocked else None,
        "total": len(payload.lead_ids),
        "results": results,
    }


@router.post("/whatsapp/batch")
async def batch_send_whatsapp(
    payload: BatchSendIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    leads = await lead_repo.get_leads_by_ids(session, account_id, payload.lead_ids)

    results = []
    sent = mocked = failed = skipped = not_attempted = 0
    blocked: Optional[send_gate.SendBlocked] = None

    for index, lead in enumerate(leads):
        if not lead.get("phone"):
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": "no phone"})
            continue
        if not consent_repo.can_send("whatsapp", lead["whatsapp_consent"]):
            skipped += 1
            results.append({"lead_id": lead["id"], "status": "skipped", "reason": "not opted in"})
            continue
        blocked = await _gate(session, account_id, "whatsapp")
        if blocked:
            for rest in leads[index:]:
                not_attempted += 1
                results.append({"lead_id": rest["id"], "status": "blocked", "reason": blocked.code})
            await _audit_batch_block(session, user, blocked, "whatsapp")
            break
        body = _render(payload.body, lead)
        result = send_whatsapp(lead["phone"], body)

        contact_id = uuid.UUID(lead["contact_id"]) if lead.get("contact_id") else None
        await outreach_repo.create_whatsapp_send(
            session,
            account_id,
            campaign_id=uuid.UUID(payload.campaign_id) if payload.campaign_id else None,
            contact_id=contact_id,
            direction="outbound",
            from_number="",
            to_number=lead["phone"],
            body=body,
            status=result["status"],
            provider_message_sid=result.get("provider_id"),
            error=result.get("error"),
        )
        await outreach_repo.record_outreach_event(
            session,
            account_id,
            channel="whatsapp",
            event_type=_event_type_for(result["status"]),
            campaign_id=payload.campaign_id,
            lead_id=lead["id"],
        )

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1
        results.append({"lead_id": lead["id"], "phone": lead["phone"], "status": result["status"]})

    if payload.campaign_id:
        await campaign_repo.increment_counters(session, account_id, payload.campaign_id, sent=sent + mocked)

    await activity_repo.record(
        session,
        user["org_id"],
        "message.whatsapp.batch",
        f"Batch WhatsApp · {sent} sent, {mocked} mocked, {failed} failed, {skipped} skipped"
        + (f", {not_attempted} not attempted ({blocked.code})" if blocked else ""),
    )
    return {
        "dispatched": sent + mocked,
        "sent": sent,
        "mocked": mocked,
        "failed": failed,
        "skipped": skipped,
        "not_attempted": not_attempted,
        "blocked": block_detail(blocked) if blocked else None,
        "total": len(payload.lead_ids),
        "results": results,
    }
