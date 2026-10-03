"""Read-only aggregates for the dashboard. Every number is computed from stored rows; nothing is estimated."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Date as SqlDate
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign, Lead, OutboundEvent, OutboundMessage, ProspectSignal, SuppressionEntry
from repositories.prospect_repo import ACTIVE, IN_DISCOVERY, _latest_scores_subquery


def _pairs(result) -> dict:
    return {row[0]: row[1] for row in result.all()}


async def prospect_kpis(session: AsyncSession, account_id: uuid.UUID) -> dict:
    by_review = {
        status: int(n)
        for status, n in (
            await session.execute(
                select(Lead.review_status, func.count())
                .where(Lead.account_id == account_id, ACTIVE, IN_DISCOVERY)
                .group_by(Lead.review_status)
            )
        ).all()
    }
    latest = _latest_scores_subquery()
    scored, avg = (
        await session.execute(
            select(func.count(latest.c.score), func.avg(latest.c.score))
            .select_from(Lead)
            .join(latest, latest.c.lead_id == Lead.id)
            .where(Lead.account_id == account_id, ACTIVE, IN_DISCOVERY)
        )
    ).one()
    return {
        "total": sum(by_review.values()),
        "by_review": {k: by_review.get(k, 0) for k in ("pending", "approved", "rejected")},
        "scored": int(scored),
        "avg_score": round(float(avg), 1) if avg is not None else None,  # None = nothing scored yet, not 0
    }


async def outbound_totals(session: AsyncSession, account_id: uuid.UUID) -> dict:
    """Messages that left (not failed), distinct replied / bounced messages, and opt-out identities."""
    sent = (
        await session.execute(
            select(func.count()).where(OutboundMessage.account_id == account_id, OutboundMessage.status != "failed")
        )
    ).scalar_one()
    events = _pairs(
        (
            await session.execute(
                select(OutboundEvent.event_type, func.count(func.distinct(OutboundEvent.message_id)))
                .join(OutboundMessage, OutboundMessage.id == OutboundEvent.message_id)
                .where(OutboundMessage.account_id == account_id, OutboundEvent.event_type.in_(("replied", "bounced")))
                .group_by(OutboundEvent.event_type)
            )
        )
    )
    unsubscribed = (
        await session.execute(
            select(func.count()).where(
                SuppressionEntry.account_id == account_id,
                SuppressionEntry.kind == "email",
                SuppressionEntry.reason == "opt_out",
            )
        )
    ).scalar_one()
    return {
        "messages": int(sent),
        "replied": int(events.get("replied", 0)),
        "bounced": int(events.get("bounced", 0)),
        "unsubscribed": int(unsubscribed),
    }


async def daily_series(session: AsyncSession, account_id: uuid.UUID, days: int, now: datetime) -> list[dict]:
    """Per UTC day: messages dispatched and replies recorded, zero-filled."""
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_day = cast(OutboundMessage.dispatched_at, SqlDate)
    sent = _pairs(
        (
            await session.execute(
                select(sent_day, func.count())
                .where(
                    OutboundMessage.account_id == account_id,
                    OutboundMessage.status != "failed",
                    OutboundMessage.dispatched_at >= start,
                )
                .group_by(sent_day)
            )
        )
    )
    reply_day = cast(OutboundEvent.created_at, SqlDate)
    replies = _pairs(
        (
            await session.execute(
                select(reply_day, func.count())
                .join(OutboundMessage, OutboundMessage.id == OutboundEvent.message_id)
                .where(
                    OutboundMessage.account_id == account_id,
                    OutboundEvent.event_type == "replied",
                    OutboundEvent.created_at >= start,
                )
                .group_by(reply_day)
            )
        )
    )
    out = []
    for i in range(days):
        day = (start + timedelta(days=i)).date()
        out.append({"date": day.isoformat(), "sent": int(sent.get(day, 0)), "replied": int(replies.get(day, 0))})
    return out


async def latest_prospects(session: AsyncSession, account_id: uuid.UUID, limit: int) -> list[dict]:
    latest = _latest_scores_subquery()
    rows = await session.execute(
        select(Lead.id, Lead.company, Lead.full_name, Lead.city, Lead.review_status, Lead.created_at, latest.c.score)
        .outerjoin(latest, latest.c.lead_id == Lead.id)
        .where(Lead.account_id == account_id, ACTIVE, IN_DISCOVERY)
        .order_by(Lead.created_at.desc(), Lead.id)
        .limit(limit)
    )
    return [
        {
            "id": str(i),
            "name": company or full_name,
            "city": city,
            "review_status": status,
            "created_at": created,
            "score": score,
        }
        for i, company, full_name, city, status, created, score in rows.all()
    ]


async def latest_detected_signals(session: AsyncSession, account_id: uuid.UUID, limit: int) -> list[dict]:
    rows = await session.execute(
        select(
            ProspectSignal.lead_id,
            Lead.company,
            Lead.full_name,
            ProspectSignal.signal_key,
            ProspectSignal.evidence,
            ProspectSignal.created_at,
        )
        .join(Lead, Lead.id == ProspectSignal.lead_id)
        .where(
            ProspectSignal.account_id == account_id,
            ProspectSignal.state == "detected",
            Lead.deleted_at.is_(None),
            IN_DISCOVERY,
        )
        .order_by(ProspectSignal.created_at.desc(), ProspectSignal.id)
        .limit(limit)
    )
    return [
        {"lead_id": str(lid), "name": company or full_name, "key": key, "evidence": evidence, "observed_at": at}
        for lid, company, full_name, key, evidence, at in rows.all()
    ]


async def campaigns(session: AsyncSession, account_id: uuid.UUID, limit: int) -> list[dict]:
    rows = await session.execute(
        select(Campaign.id, Campaign.name, Campaign.status, Campaign.sent, Campaign.opened, Campaign.replied)
        .where(Campaign.account_id == account_id, Campaign.deleted_at.is_(None))
        .order_by(Campaign.created_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(i), "name": name, "status": status, "sent": sent, "opened": opened, "replied": replied}
        for i, name, status, sent, opened, replied in rows.all()
    ]


async def inbox(session: AsyncSession, account_id: uuid.UUID, limit: int) -> list[dict]:
    rows = await session.execute(
        select(
            OutboundEvent.message_id,
            OutboundMessage.lead_id,
            Lead.company,
            Lead.full_name,
            OutboundEvent.detail,
            OutboundEvent.created_at,
        )
        .join(OutboundMessage, OutboundMessage.id == OutboundEvent.message_id)
        .join(Lead, Lead.id == OutboundMessage.lead_id)
        .where(OutboundMessage.account_id == account_id, OutboundEvent.event_type == "replied")
        .order_by(OutboundEvent.created_at.desc(), OutboundEvent.id)
        .limit(limit)
    )
    out = []
    for mid, lid, company, full_name, detail, at in rows.all():
        excerpt: Optional[str] = (detail or {}).get("excerpt") or None  # blanked by an erasure request
        out.append(
            {
                "message_id": str(mid),
                "lead_id": str(lid),
                "name": company or full_name,
                "excerpt": excerpt,
                "simulated": bool((detail or {}).get("simulated")),
                "at": at,
            }
        )
    return out


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
