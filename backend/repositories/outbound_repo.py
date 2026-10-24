"""Outbound dispatch ledger: messages, lifecycle events, and the counters the send limits are computed from."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EmailSend, OutboundEvent, OutboundMessage, WhatsappSend


async def get_by_key(session: AsyncSession, account_id: uuid.UUID, key: str) -> Optional[OutboundMessage]:
    return (
        await session.execute(
            select(OutboundMessage).where(
                OutboundMessage.account_id == account_id, OutboundMessage.idempotency_key == key
            )
        )
    ).scalar_one_or_none()


async def get_for_draft(session: AsyncSession, account_id: uuid.UUID, draft_id: uuid.UUID) -> Optional[OutboundMessage]:
    """The message already produced from a draft, if any (a failed attempt does not count: it may be retried)."""
    return (
        await session.execute(
            select(OutboundMessage)
            .where(
                OutboundMessage.account_id == account_id,
                OutboundMessage.draft_id == draft_id,
                OutboundMessage.status != "failed",
            )
            .order_by(OutboundMessage.dispatched_at)
            .limit(1)
        )
    ).scalar_one_or_none()


async def count_failed_for_draft(session: AsyncSession, account_id: uuid.UUID, draft_id: uuid.UUID) -> int:
    """How many attempts on this draft ended `failed`: the next default idempotency key depends on it."""
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(OutboundMessage)
                .where(
                    OutboundMessage.account_id == account_id,
                    OutboundMessage.draft_id == draft_id,
                    OutboundMessage.status == "failed",
                )
            )
        ).scalar_one()
    )


async def create_idempotent(
    session: AsyncSession, account_id: uuid.UUID, *, idempotency_key: str, **fields: object
) -> tuple[OutboundMessage, bool]:
    """Insert a message, or return the existing one for the key (second item False)."""
    stmt = (
        pg_insert(OutboundMessage)
        .values(account_id=account_id, idempotency_key=idempotency_key, **fields)
        .on_conflict_do_nothing(index_elements=["account_id", "idempotency_key"])
        .returning(OutboundMessage.id)
    )
    created = (await session.execute(stmt)).scalar_one_or_none() is not None
    message = await get_by_key(session, account_id, idempotency_key)
    assert message is not None
    return message, created


async def add_event(
    session: AsyncSession, account_id: uuid.UUID, message_id: uuid.UUID, event_type: str, detail: Optional[dict] = None
) -> OutboundEvent:
    event = OutboundEvent(account_id=account_id, message_id=message_id, event_type=event_type, detail=detail or {})
    session.add(event)
    await session.flush()
    return event


async def get(session: AsyncSession, account_id: uuid.UUID, message_id: str) -> Optional[OutboundMessage]:
    try:
        mid = uuid.UUID(message_id)
    except ValueError:
        return None
    return (
        await session.execute(
            select(OutboundMessage).where(OutboundMessage.id == mid, OutboundMessage.account_id == account_id)
        )
    ).scalar_one_or_none()


async def list_messages(
    session: AsyncSession, account_id: uuid.UUID, *, status: Optional[str] = None, limit: int = 50, offset: int = 0
) -> list[OutboundMessage]:
    query = select(OutboundMessage).where(OutboundMessage.account_id == account_id)
    if status:
        query = query.where(OutboundMessage.status == status)
    rows = await session.execute(
        query.order_by(OutboundMessage.dispatched_at.desc(), OutboundMessage.id).limit(limit).offset(offset)
    )
    return list(rows.scalars())


async def ids_for_lead(session: AsyncSession, account_id: uuid.UUID, lead_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.execute(
        select(OutboundMessage.id).where(OutboundMessage.account_id == account_id, OutboundMessage.lead_id == lead_id)
    )
    return [mid for (mid,) in rows.all()]


async def events_of(session: AsyncSession, message_id: uuid.UUID) -> list[OutboundEvent]:
    rows = await session.execute(
        select(OutboundEvent)
        .where(OutboundEvent.message_id == message_id)
        .order_by(OutboundEvent.created_at, OutboundEvent.id)
    )
    return list(rows.scalars())


async def dispatch_times_since(
    session: AsyncSession, account_id: uuid.UUID, channel: str, since: datetime
) -> list[datetime]:
    """Times of every outbound send since `since`, from ALL paths — what the send limits count.

    The prospect ledger (`outbound_messages`) plus the legacy per-channel tables (`email_sends`, `whatsapp_sends`), so a
    campaign or a manual send counts against the same cap as a dispatch. Failed attempts do not count.
    """
    times: list[datetime] = []
    ledger = await session.execute(
        select(OutboundMessage.dispatched_at).where(
            OutboundMessage.account_id == account_id,
            OutboundMessage.channel == channel,
            OutboundMessage.dispatched_at >= since,
            OutboundMessage.status != "failed",
        )
    )
    times += [t for (t,) in ledger.all()]
    if channel == "email":
        legacy = await session.execute(
            select(EmailSend.created_at).where(
                EmailSend.account_id == account_id, EmailSend.created_at >= since, EmailSend.status != "failed"
            )
        )
    else:
        legacy = await session.execute(
            select(WhatsappSend.created_at).where(
                WhatsappSend.account_id == account_id,
                WhatsappSend.direction == "outbound",
                WhatsappSend.created_at >= since,
                WhatsappSend.status != "failed",
            )
        )
    times += [t for (t,) in legacy.all()]
    return times


# ---------------------------------------------------------------- inbound mailbox
async def find_by_provider_ids(session: AsyncSession, provider_ids: list[str]) -> list[OutboundMessage]:
    """Messages (any organisation: the mailbox is the server's) whose SMTP Message-ID is one of `provider_ids`."""
    if not provider_ids:
        return []
    rows = await session.execute(select(OutboundMessage).where(OutboundMessage.provider_message_id.in_(provider_ids)))
    return list(rows.scalars())


async def latest_sent_to(session: AsyncSession, email: str) -> Optional[OutboundMessage]:
    rows = await session.execute(
        select(OutboundMessage)
        .where(OutboundMessage.to_email == email, OutboundMessage.status.in_(("sent", "replied")))
        .order_by(OutboundMessage.dispatched_at.desc())
        .limit(1)
    )
    return rows.scalar_one_or_none()


async def has_inbound_event(session: AsyncSession, message_id: uuid.UUID, inbound_id: str) -> bool:
    """Idempotence: an inbound e-mail already recorded on this message is never recorded twice."""
    rows = await session.execute(
        select(OutboundEvent.id)
        .where(OutboundEvent.message_id == message_id, OutboundEvent.detail["inbound_message_id"].astext == inbound_id)
        .limit(1)
    )
    return rows.first() is not None
