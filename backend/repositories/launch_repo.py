"""SQL of the individual campaigns: the pool of prospects to pick from, the bulk facts the exclusions rest on, and the
plan rows (`campaign_dispatches`). The only place that touches these tables; the rules themselves live in
services/outreach_os/campaign_plan.py (pure) and the orchestration in services/campaign_launch.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import and_, false, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Campaign,
    CampaignDispatch,
    CampaignLead,
    Contact,
    DraftJob,
    Lead,
    MessageDraft,
    OutboundEvent,
    OutboundMessage,
    OutreachEvent,
    ProspectSource,
)
from repositories import consent_repo, eligibility_sql, heat_sql
from repositories.prospect_repo import ACTIVE, IN_DISCOVERY

ACTIVE_DISPATCH = ("scheduled", "sending")


def _flag(expression: Any) -> Any:
    return func.coalesce(expression, false())


def _flagged(  # type: ignore[no-untyped-def]
    account_id: uuid.UUID, now: Optional[datetime], zone: Optional[dict[str, Any]] = None
):
    """Prospect + the four facts the selection needs, computed by the same SQL as the map (one policy, one decision)."""
    src = eligibility_sql.latest_source(account_id)
    scores = heat_sql.latest_scores()
    stmt = (
        select(
            Lead,
            _flag(eligibility_sql.qualified(src, now)).label("qualified"),
            _flag(eligibility_sql.suppressed()).label("suppressed"),
            _flag(eligibility_sql.opted_out()).label("opted_out"),
            _flag(eligibility_sql.confirmed_demo()).label("demo"),
        )
        .outerjoin(src, src.c.lead_id == Lead.id)
        .outerjoin(scores, scores.c.lead_id == Lead.id)
        .where(Lead.account_id == account_id, ACTIVE, IN_DISCOVERY)
    )
    if zone is not None:  # only prospects positioned inside the perimeter (a prospect with no position is outside)
        stmt = stmt.where(
            src.c.lat.between(float(zone["south"]), float(zone["north"])),
            src.c.lon.between(float(zone["west"]), float(zone["east"])),
        )
    rank = (
        eligibility_sql.hot(src, now).desc(),
        heat_sql.heat_sql(scores.c.score).desc(),
        Lead.created_at.desc(),
        Lead.id,
    )
    return stmt, rank


async def pool(
    session: AsyncSession, account_id: uuid.UUID, now: datetime, limit: int, zone: Optional[dict[str, Any]] = None
) -> list[Any]:
    """Approved prospects, best first: rows of (lead, qualified, suppressed, opted_out, demo). `zone` = a perimeter."""
    stmt, rank = _flagged(account_id, now, zone)
    rows = await session.execute(stmt.where(Lead.review_status == "approved").order_by(*rank).limit(limit))
    return list(rows.all())


async def flags_for(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID], now: datetime
) -> dict[uuid.UUID, Any]:
    stmt, _ = _flagged(account_id, now)
    rows = await session.execute(stmt.where(Lead.id.in_(list(lead_ids))))
    return {row[0].id: row for row in rows.all()}


async def review_counts(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    """Prospects of the discovery by review state: how many are not (yet) approved, for the selection summary."""
    rows = await session.execute(
        select(Lead.review_status, func.count())
        .where(Lead.account_id == account_id, ACTIVE, IN_DISCOVERY)
        .group_by(Lead.review_status)
    )
    return {status: int(n) for status, n in rows.all()}


# ---------------------------------------------------------------------------------------------- bulk facts
async def replied_lead_ids(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Prospects who answered: a message of the send ledger marked replied, or an inbound reply on the timeline."""
    ids = list(lead_ids)
    if not ids:
        return set()
    ledger = await session.execute(
        select(OutboundMessage.lead_id).where(
            OutboundMessage.account_id == account_id,
            OutboundMessage.lead_id.in_(ids),
            OutboundMessage.status == "replied",
        )
    )
    timeline = await session.execute(
        select(OutreachEvent.lead_id).where(
            OutreachEvent.account_id == account_id,
            OutreachEvent.lead_id.in_(ids),
            OutreachEvent.direction == "inbound",
            OutreachEvent.event_type == "replied",
        )
    )
    return {lid for (lid,) in ledger.all() if lid} | {lid for (lid,) in timeline.all() if lid}


async def opted_out_message_lead_ids(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Prospects whose message carries an `opted_out` event (the opposition that came with a reply)."""
    ids = list(lead_ids)
    if not ids:
        return set()
    rows = await session.execute(
        select(OutboundMessage.lead_id)
        .join(OutboundEvent, OutboundEvent.message_id == OutboundMessage.id)
        .where(
            OutboundMessage.account_id == account_id,
            OutboundMessage.lead_id.in_(ids),
            OutboundEvent.event_type == "opted_out",
        )
    )
    return {lid for (lid,) in rows.all()}


async def contacted_lead_ids(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Prospects who already got (or are getting) a message: sent, in flight, replied or bounced; a failed attempt does
    not count."""
    ids = list(lead_ids)
    if not ids:
        return set()
    rows = await session.execute(
        select(OutboundMessage.lead_id).where(
            OutboundMessage.account_id == account_id,
            OutboundMessage.lead_id.in_(ids),
            OutboundMessage.status != "failed",
        )
    )
    return {lid for (lid,) in rows.all()}


async def bounced_emails(session: AsyncSession, account_id: uuid.UUID, emails: Sequence[str]) -> set[str]:
    wanted = [e.lower() for e in emails if e]
    if not wanted:
        return set()
    rows = await session.execute(
        select(func.lower(OutboundMessage.to_email)).where(
            OutboundMessage.account_id == account_id,
            func.lower(OutboundMessage.to_email).in_(wanted),
            OutboundMessage.status == "bounced",
        )
    )
    return {e for (e,) in rows.all() if e}


async def taken_elsewhere(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: Optional[uuid.UUID], lead_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Prospects already engaged by ANOTHER campaign: a message planned or in flight, a running campaign, or a selection
    that another individual campaign still holds."""
    ids = list(lead_ids)
    if not ids:
        return set()
    other_campaign = Campaign.id != campaign_id if campaign_id is not None else Campaign.id.is_not(None)
    other_dispatch = (
        CampaignDispatch.campaign_id != campaign_id
        if campaign_id is not None
        else CampaignDispatch.campaign_id.is_not(None)
    )
    planned = await session.execute(
        select(CampaignDispatch.lead_id).where(
            CampaignDispatch.account_id == account_id,
            CampaignDispatch.lead_id.in_(ids),
            CampaignDispatch.status.in_(ACTIVE_DISPATCH),
            other_dispatch,
        )
    )
    held = await session.execute(
        select(CampaignLead.lead_id)
        .join(Campaign, Campaign.id == CampaignLead.campaign_id)
        .where(
            Campaign.account_id == account_id,
            Campaign.deleted_at.is_(None),
            CampaignLead.lead_id.in_(ids),
            other_campaign,
            or_(
                Campaign.status == "running",
                and_(Campaign.kind == "individual", Campaign.status.in_(("draft", "paused"))),
            ),
        )
    )
    return {lid for (lid,) in planned.all()} | {lid for (lid,) in held.all()}


async def primary_consent(session: AsyncSession, lead_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The e-mail consent of each prospect's primary contact ("unknown" when nothing was ever recorded)."""
    ids = list(lead_ids)
    if not ids:
        return {}
    contacts = await session.execute(
        select(Contact.lead_id, Contact.id)
        .where(Contact.lead_id.in_(ids), Contact.deleted_at.is_(None))
        .order_by(Contact.is_primary.desc(), Contact.created_at.asc())
    )
    contact_of: dict[uuid.UUID, uuid.UUID] = {}
    for lead_id, contact_id in contacts.all():
        contact_of.setdefault(lead_id, contact_id)
    status_of = await consent_repo.get_status_map(session, list(contact_of.values()), "email")
    return {lid: status_of.get(contact_of[lid], consent_repo.DEFAULT_STATUS) for lid in contact_of} | {
        lid: consent_repo.DEFAULT_STATUS for lid in ids if lid not in contact_of
    }


async def license_notes(session: AsyncSession, lead_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Optional[str]]]:
    ids = list(lead_ids)
    out: dict[uuid.UUID, list[Optional[str]]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = await session.execute(
        select(ProspectSource.lead_id, ProspectSource.license_note)
        .where(ProspectSource.lead_id.in_(ids))
        .order_by(ProspectSource.fetched_at.asc())
    )
    for lead_id, note in rows.all():
        out[lead_id].append(note)
    return out


async def latest_drafts(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, MessageDraft]:
    """The most recent draft of each prospect (the one the review shows and approves)."""
    ids = list(lead_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(MessageDraft)
        .where(MessageDraft.account_id == account_id, MessageDraft.lead_id.in_(ids))
        .distinct(MessageDraft.lead_id)
        .order_by(MessageDraft.lead_id, MessageDraft.created_at.desc(), MessageDraft.id)
    )
    return {d.lead_id: d for d in rows.scalars()}


async def latest_jobs(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, DraftJob]:
    ids = list(lead_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(DraftJob)
        .where(DraftJob.account_id == account_id, DraftJob.lead_id.in_(ids))
        .distinct(DraftJob.lead_id)
        .order_by(DraftJob.lead_id, DraftJob.created_at.desc(), DraftJob.id)
    )
    return {j.lead_id: j for j in rows.scalars()}


async def messages_of(
    session: AsyncSession, account_id: uuid.UUID, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, OutboundMessage]:
    ids = [m for m in message_ids if m]
    if not ids:
        return {}
    rows = await session.execute(
        select(OutboundMessage).where(OutboundMessage.account_id == account_id, OutboundMessage.id.in_(ids))
    )
    return {m.id: m for m in rows.scalars()}


# ---------------------------------------------------------------------------------------------- plan rows
async def dispatches_of(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID
) -> dict[uuid.UUID, CampaignDispatch]:
    rows = await session.execute(
        select(CampaignDispatch).where(
            CampaignDispatch.account_id == account_id, CampaignDispatch.campaign_id == campaign_id
        )
    )
    return {d.lead_id: d for d in rows.scalars()}


async def planned_times(session: AsyncSession, account_id: uuid.UUID) -> list[datetime]:
    """When the messages already planned (any campaign) are due: they occupy the limits before they leave."""
    rows = await session.execute(
        select(CampaignDispatch.planned_at).where(
            CampaignDispatch.account_id == account_id, CampaignDispatch.status.in_(ACTIVE_DISPATCH)
        )
    )
    return [t for (t,) in rows.all()]


async def plan(
    session: AsyncSession,
    account_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    lead_id: uuid.UUID,
    draft_id: uuid.UUID,
    to_email: str,
    planned_at: datetime,
    user_id: Optional[uuid.UUID],
    existing: Optional[CampaignDispatch],
) -> CampaignDispatch:
    """Plan one message, or plan it again after a person cancelled it or a gate stopped it (never an accepted or unknown
    one)."""
    if existing is not None:
        existing.draft_id = draft_id
        existing.to_email = to_email
        existing.status = "scheduled"
        existing.planned_at = planned_at
        existing.attempts = 0
        existing.last_reason = None
        existing.message_id = None
        existing.created_by_user_id = user_id
        await session.flush()
        return existing
    row = CampaignDispatch(
        account_id=account_id,
        campaign_id=campaign_id,
        lead_id=lead_id,
        draft_id=draft_id,
        to_email=to_email,
        status="scheduled",
        planned_at=planned_at,
        created_by_user_id=user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def due_ids(
    session: AsyncSession, now: datetime, limit: int, account_id: Optional[uuid.UUID] = None
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(row id, account id) of the messages whose time has come, oldest first."""
    stmt = select(CampaignDispatch.id, CampaignDispatch.account_id).where(
        CampaignDispatch.status == "scheduled", CampaignDispatch.planned_at <= now
    )
    if account_id is not None:
        stmt = stmt.where(CampaignDispatch.account_id == account_id)
    rows = await session.execute(stmt.order_by(CampaignDispatch.planned_at, CampaignDispatch.id).limit(limit))
    return [(row_id, owner) for row_id, owner in rows.all()]


async def claim(session: AsyncSession, dispatch_id: uuid.UUID, now: datetime) -> Optional[CampaignDispatch]:
    """Take a due row for sending: atomic, two workers can never both send it. None when it is not due (any more)."""
    taken = (
        await session.execute(
            update(CampaignDispatch)
            .where(
                CampaignDispatch.id == dispatch_id,
                CampaignDispatch.status == "scheduled",
                CampaignDispatch.planned_at <= now,
            )
            .values(status="sending", attempts=CampaignDispatch.attempts + 1, last_checked_at=now, updated_at=now)
            .returning(CampaignDispatch.id)
        )
    ).scalar_one_or_none()
    if taken is None:
        return None
    return (await session.execute(select(CampaignDispatch).where(CampaignDispatch.id == taken))).scalar_one()


async def stuck(session: AsyncSession, now: datetime, older_than: timedelta) -> list[CampaignDispatch]:
    rows = await session.execute(
        select(CampaignDispatch).where(
            CampaignDispatch.status == "sending", CampaignDispatch.updated_at <= now - older_than
        )
    )
    return list(rows.scalars())


async def counts(session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID) -> dict[str, int]:
    rows = await session.execute(
        select(CampaignDispatch.status, func.count())
        .where(CampaignDispatch.account_id == account_id, CampaignDispatch.campaign_id == campaign_id)
        .group_by(CampaignDispatch.status)
    )
    return {status: int(n) for status, n in rows.all()}


async def cancel_scheduled(session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID, now: datetime) -> int:
    result = await session.execute(
        update(CampaignDispatch)
        .where(
            CampaignDispatch.account_id == account_id,
            CampaignDispatch.campaign_id == campaign_id,
            CampaignDispatch.status == "scheduled",
        )
        .values(status="cancelled", last_reason="cancelled_by_user", updated_at=now)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def selection_of(session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID) -> list[uuid.UUID]:
    """The recipients picked for the campaign, in the order they were picked."""
    rows = await session.execute(
        select(CampaignLead.lead_id)
        .join(Campaign, Campaign.id == CampaignLead.campaign_id)
        .where(CampaignLead.campaign_id == campaign_id, Campaign.account_id == account_id)
        .order_by(CampaignLead.assigned_at, CampaignLead.lead_id)
    )
    return list(rows.scalars())


async def launches(session: AsyncSession, account_id: uuid.UUID) -> list[Campaign]:
    rows = await session.execute(
        select(Campaign)
        .where(Campaign.account_id == account_id, Campaign.kind == "individual", Campaign.deleted_at.is_(None))
        .order_by(Campaign.created_at.desc())
    )
    return list(rows.scalars())


async def names_of(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, Optional[str]]]:
    ids = list(lead_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(Lead.id, Lead.full_name, Lead.city).where(Lead.account_id == account_id, Lead.id.in_(ids))
    )
    return {lead_id: (name, city) for lead_id, name, city in rows.all()}
