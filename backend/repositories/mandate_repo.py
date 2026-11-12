"""SQL of the bounded automatic mode: the mandates, their append-only journal and what their stop rules observe.
Everything is scoped by `account_id` except `active_all`, which the scheduled run uses to visit every account."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AutomationMandate, CampaignDispatch, MandateEvent, OutboundEvent, OutboundMessage


async def get(session: AsyncSession, account_id: uuid.UUID, mandate_id: uuid.UUID) -> Optional[AutomationMandate]:
    result = await session.execute(
        select(AutomationMandate).where(AutomationMandate.id == mandate_id, AutomationMandate.account_id == account_id)
    )
    return result.scalar_one_or_none()


async def by_id(session: AsyncSession, mandate_id: uuid.UUID) -> Optional[AutomationMandate]:
    """Without an account: only for a message's send-time gate, which already holds the approval that names it."""
    return await session.get(AutomationMandate, mandate_id)


async def listing(session: AsyncSession, account_id: uuid.UUID) -> list[AutomationMandate]:
    result = await session.execute(
        select(AutomationMandate)
        .where(AutomationMandate.account_id == account_id)
        .order_by(AutomationMandate.created_at.desc())
    )
    return list(result.scalars())


async def active_all(session: AsyncSession) -> list[AutomationMandate]:
    result = await session.execute(select(AutomationMandate).where(AutomationMandate.status == "active"))
    return list(result.scalars())


async def active_for_campaign(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID
) -> Optional[AutomationMandate]:
    result = await session.execute(
        select(AutomationMandate).where(
            AutomationMandate.account_id == account_id,
            AutomationMandate.campaign_id == campaign_id,
            AutomationMandate.status.in_(("draft", "active", "suspended")),
        )
    )
    return result.scalars().first()


async def log(
    session: AsyncSession,
    mandate: AutomationMandate,
    action: str,
    *,
    actor_user_id: Optional[uuid.UUID] = None,
    detail: Optional[dict[str, Any]] = None,
) -> MandateEvent:
    """One line of the journal (never edited, never deleted): who did what to this mandate, or what was decided."""
    event = MandateEvent(
        account_id=mandate.account_id,
        mandate_id=mandate.id,
        action=action,
        actor_type="user" if actor_user_id else "system",
        actor_user_id=actor_user_id,
        detail=detail or {},
    )
    session.add(event)
    await session.flush()
    return event


async def events(session: AsyncSession, mandate_id: uuid.UUID, limit: int = 50) -> list[MandateEvent]:
    result = await session.execute(
        select(MandateEvent)
        .where(MandateEvent.mandate_id == mandate_id)
        .order_by(MandateEvent.created_at.desc(), MandateEvent.id.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def last_event(session: AsyncSession, mandate_id: uuid.UUID, action: str) -> Optional[MandateEvent]:
    result = await session.execute(
        select(MandateEvent)
        .where(MandateEvent.mandate_id == mandate_id, MandateEvent.action == action)
        .order_by(MandateEvent.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------------------------- observations
async def message_counts(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID, since: Optional[datetime] = None
) -> dict[str, int]:
    """What came of the campaign's messages: sent (left or may have), bounced, replied, opposed."""
    base = (
        select(OutboundMessage.id, OutboundMessage.status)
        .join(CampaignDispatch, CampaignDispatch.message_id == OutboundMessage.id)
        .where(CampaignDispatch.account_id == account_id, CampaignDispatch.campaign_id == campaign_id)
    )
    if since is not None:
        base = base.where(OutboundMessage.dispatched_at >= since)
    rows = (await session.execute(base)).all()
    ids = [r[0] for r in rows]
    opted = 0
    if ids:
        opted = int(
            (
                await session.execute(
                    select(func.count(func.distinct(OutboundEvent.message_id))).where(
                        OutboundEvent.message_id.in_(ids), OutboundEvent.event_type == "opted_out"
                    )
                )
            ).scalar_one()
        )
    statuses = [r[1] for r in rows]
    return {
        "sent": len([s for s in statuses if s in ("sent", "bounced", "replied", "sending")]),
        "bounced": statuses.count("bounced"),
        "replied": statuses.count("replied"),
        "opted_out": opted,
    }


async def auth_error_since(session: AsyncSession, account_id: uuid.UUID, since: datetime) -> bool:
    """Did the mail server refuse our credentials recently? (A failed message whose error says so.)"""
    count = (
        await session.execute(
            select(func.count()).where(
                OutboundMessage.account_id == account_id,
                OutboundMessage.status == "failed",
                OutboundMessage.dispatched_at >= since,
                OutboundMessage.error.ilike("authentication failed%"),
            )
        )
    ).scalar_one()
    return int(count) > 0


async def last_handled_at(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID, exclude: Optional[uuid.UUID] = None
) -> Optional[datetime]:
    """When the campaign's latest message was handled: the reference for the mandate's own cadence. `exclude` is the
    message being decided now (it is "in flight" because it was claimed: it is not the one that came before it)."""
    stmt = select(func.max(CampaignDispatch.last_checked_at)).where(
        CampaignDispatch.account_id == account_id,
        CampaignDispatch.campaign_id == campaign_id,
        CampaignDispatch.status.in_(("accepted", "sending", "unknown")),
    )
    if exclude is not None:
        stmt = stmt.where(CampaignDispatch.id != exclude)
    return (await session.execute(stmt)).scalar_one_or_none()
