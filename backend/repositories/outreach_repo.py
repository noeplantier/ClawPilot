"""Email/WhatsApp send persistence + webhook event log + unified outreach timeline.

Replaces the legacy polymorphic `messages` Mongo collection with two typed
tables (`email_sends`/`whatsapp_sends` — plan doc section 1.11-1.13) and adds
`webhook_events` as a durable receipt log so a SendGrid/Twilio callback is never
silently lost even if downstream processing fails.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Contact, EmailSend, OutreachEvent, WebhookEvent, WhatsappSend


def email_to_message(s: EmailSend, lead_id: Optional[uuid.UUID] = None) -> dict:
    return {
        "id": str(s.id),
        "org_id": str(s.account_id),
        "campaign_id": str(s.campaign_id) if s.campaign_id else None,
        "lead_id": str(lead_id) if lead_id else None,
        "contact_id": str(s.contact_id) if s.contact_id else None,
        "channel": "email",
        "direction": "outbound",
        "to": s.to_email,
        "subject": s.subject,
        "body": s.body,
        "status": s.status,
        "provider_id": s.provider_message_id,
        "error": s.error,
        "created_at": s.created_at,
    }


def whatsapp_to_message(s: WhatsappSend, lead_id: Optional[uuid.UUID] = None) -> dict:
    return {
        "id": str(s.id),
        "org_id": str(s.account_id) if s.account_id else None,
        "campaign_id": str(s.campaign_id) if s.campaign_id else None,
        "lead_id": str(lead_id) if lead_id else None,
        "contact_id": str(s.contact_id) if s.contact_id else None,
        "channel": "whatsapp",
        "direction": s.direction,
        "to": s.to_number,
        "subject": None,
        "body": s.body,
        "status": s.status,
        "provider_id": s.provider_message_sid,
        "error": s.error,
        "created_at": s.created_at,
    }


async def create_email_send(session: AsyncSession, account_id: uuid.UUID, **kwargs) -> EmailSend:
    send = EmailSend(account_id=account_id, **kwargs)
    session.add(send)
    await session.flush()
    return send


async def create_whatsapp_send(session: AsyncSession, account_id: Optional[uuid.UUID], **kwargs) -> WhatsappSend:
    send = WhatsappSend(account_id=account_id, **kwargs)
    session.add(send)
    await session.flush()
    return send


async def list_messages(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    channel: Optional[str] = None,
    lead_id: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    items: list[dict] = []
    if channel in (None, "email"):
        email_stmt = (
            select(EmailSend, Contact.lead_id)
            .outerjoin(Contact, Contact.id == EmailSend.contact_id)
            .where(EmailSend.account_id == account_id)
        )
        if lead_id:
            email_stmt = email_stmt.where(Contact.lead_id == uuid.UUID(lead_id))
        email_result = await session.execute(email_stmt.order_by(EmailSend.created_at.desc()).limit(limit))
        items.extend(email_to_message(s, lid) for s, lid in email_result.all())
    if channel in (None, "whatsapp"):
        whatsapp_stmt = (
            select(WhatsappSend, Contact.lead_id)
            .outerjoin(Contact, Contact.id == WhatsappSend.contact_id)
            .where(WhatsappSend.account_id == account_id)
        )
        if lead_id:
            whatsapp_stmt = whatsapp_stmt.where(Contact.lead_id == uuid.UUID(lead_id))
        whatsapp_result = await session.execute(whatsapp_stmt.order_by(WhatsappSend.created_at.desc()).limit(limit))
        items.extend(whatsapp_to_message(s, lid) for s, lid in whatsapp_result.all())
    items.sort(key=lambda m: m["created_at"], reverse=True)
    return items[:limit]


async def daily_event_counts(
    session: AsyncSession, account_id: uuid.UUID, days: int = 14
) -> dict[tuple[str, str], int]:
    """Real per-day counts by event_type, keyed by (YYYY-MM-DD, event_type) —
    replaces the legacy synthetic `random.seed(hash(org_id))` timeseries."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(func.date(OutreachEvent.occurred_at), OutreachEvent.event_type, func.count())
        .where(OutreachEvent.account_id == account_id, OutreachEvent.occurred_at >= since)
        .group_by(func.date(OutreachEvent.occurred_at), OutreachEvent.event_type)
    )
    return {(str(day), event_type): count for day, event_type, count in result.all()}


async def channel_send_counts(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    """Real per-channel share of `sent` events, replacing the dashboard's old
    hardcoded 68/32 email/WhatsApp split."""
    from sqlalchemy import func

    result = await session.execute(
        select(OutreachEvent.channel, func.count())
        .where(OutreachEvent.account_id == account_id, OutreachEvent.event_type == "sent")
        .group_by(OutreachEvent.channel)
    )
    return {channel: count for channel, count in result.all()}


async def record_outreach_event(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    channel: str,
    event_type: str,
    direction: str = "outbound",
    campaign_id: Optional[str] = None,
    campaign_step_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> OutreachEvent:
    event = OutreachEvent(
        account_id=account_id,
        campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
        campaign_step_id=uuid.UUID(campaign_step_id) if campaign_step_id else None,
        lead_id=uuid.UUID(lead_id) if lead_id else None,
        contact_id=uuid.UUID(contact_id) if contact_id else None,
        channel=channel,
        event_type=event_type,
        direction=direction,
        meta=meta or {},
    )
    session.add(event)
    await session.flush()
    return event


async def list_queued_events(session: AsyncSession, account_id: uuid.UUID, campaign_id: str) -> list[OutreachEvent]:
    """`queued` events double as the scheduler's bookkeeping table — see
    services/scheduler.py, which stores the Celery task id in `meta` and reads
    real-time status back from Celery's result backend rather than duplicating
    it here."""
    result = await session.execute(
        select(OutreachEvent).where(
            OutreachEvent.account_id == account_id,
            OutreachEvent.campaign_id == uuid.UUID(campaign_id),
            OutreachEvent.event_type == "queued",
        )
    )
    return list(result.scalars().all())


async def log_webhook_event(
    session: AsyncSession, provider: str, event_type: Optional[str], raw_payload: dict
) -> WebhookEvent:
    event = WebhookEvent(provider=provider, event_type=event_type, raw_payload=raw_payload)
    session.add(event)
    await session.flush()
    return event


async def mark_webhook_processed(session: AsyncSession, event: WebhookEvent, *, error: Optional[str] = None) -> None:
    from sqlalchemy import func

    event.processed = error is None
    event.processed_at = func.now()
    event.error = error


# --- rank used to only ever upgrade a send's status forward, mirrors legacy webhook logic ---
_STATUS_RANK = {
    "queued": 0,
    "mock": 0,
    "sent": 1,
    "delivered": 2,
    "opened": 3,
    "clicked": 3,
    "replied": 4,
    "failed": -1,
    "bounced": -1,
}


async def upgrade_email_status_by_provider_id(session: AsyncSession, sg_message_id: str) -> Optional[EmailSend]:
    """Find an email_send by exact provider_message_id or by its dot-stripped
    prefix (SendGrid appends a suffix — see the generated `provider_message_id_base`
    column, plan doc section 1.12)."""
    base_id = sg_message_id.split(".")[0] if sg_message_id else None
    result = await session.execute(
        select(EmailSend).where(
            (EmailSend.provider_message_id == sg_message_id)
            | (EmailSend.provider_message_id_base == base_id if base_id else False)
        )
    )
    return result.scalars().first()


async def upgrade_whatsapp_status_by_sid(session: AsyncSession, message_sid: str) -> Optional[WhatsappSend]:
    result = await session.execute(select(WhatsappSend).where(WhatsappSend.provider_message_sid == message_sid))
    return result.scalar_one_or_none()


def status_rank(status: str) -> int:
    return _STATUS_RANK.get(status, 0)
