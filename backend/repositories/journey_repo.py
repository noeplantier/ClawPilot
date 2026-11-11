"""SQL of the "zone -> draft -> approval" journey: template versions, approvals, coverage of a zone, sent counters.
Everything is scoped by `account_id`; the rules live in services/outreach_os/campaign_template.py (pure) and the
orchestration in services/journey.py."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign, CampaignApproval, CampaignDispatch, CampaignTemplate, MapSearchJob


async def latest_template(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID
) -> Optional[CampaignTemplate]:
    result = await session.execute(
        select(CampaignTemplate)
        .where(CampaignTemplate.account_id == account_id, CampaignTemplate.campaign_id == campaign_id)
        .order_by(CampaignTemplate.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def template_version(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID, version: int
) -> Optional[CampaignTemplate]:
    result = await session.execute(
        select(CampaignTemplate).where(
            CampaignTemplate.account_id == account_id,
            CampaignTemplate.campaign_id == campaign_id,
            CampaignTemplate.version == version,
        )
    )
    return result.scalar_one_or_none()


async def add_template(
    session: AsyncSession,
    account_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    subject: str,
    body: str,
    content_hash: str,
    offer_hash: Optional[str],
    user_id: Optional[uuid.UUID],
) -> CampaignTemplate:
    """A new version (versions are never edited: the one that was approved stays as it was)."""
    last = await latest_template(session, account_id, campaign_id)
    row = CampaignTemplate(
        account_id=account_id,
        campaign_id=campaign_id,
        version=(last.version + 1) if last else 1,
        subject=subject,
        body=body,
        content_hash=content_hash,
        offer_hash=offer_hash,
        created_by_user_id=user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def latest_approval(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: uuid.UUID
) -> Optional[CampaignApproval]:
    result = await session.execute(
        select(CampaignApproval)
        .where(CampaignApproval.account_id == account_id, CampaignApproval.campaign_id == campaign_id)
        .order_by(CampaignApproval.created_at.desc(), CampaignApproval.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def add_approval(session: AsyncSession, row: CampaignApproval) -> CampaignApproval:
    session.add(row)
    await session.flush()
    return row


async def journeys(session: AsyncSession, account_id: uuid.UUID) -> list[Campaign]:
    result = await session.execute(
        select(Campaign)
        .where(Campaign.account_id == account_id, Campaign.zone.is_not(None), Campaign.deleted_at.is_(None))
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars())


async def coverage_job(session: AsyncSession, account_id: uuid.UUID, zone: dict[str, Any]) -> Optional[MapSearchJob]:
    """The latest finished map search whose box contains the zone (the search that really looked at this perimeter)."""
    result = await session.execute(
        select(MapSearchJob)
        .where(
            MapSearchJob.account_id == account_id,
            MapSearchJob.status == "succeeded",
            MapSearchJob.south <= float(zone["south"]),
            MapSearchJob.west <= float(zone["west"]),
            MapSearchJob.north >= float(zone["north"]),
            MapSearchJob.east >= float(zone["east"]),
        )
        .order_by(MapSearchJob.finished_at.desc().nullslast(), MapSearchJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def sent_count(
    session: AsyncSession,
    account_id: uuid.UUID,
    campaign_id: uuid.UUID,
    since: Optional[datetime] = None,
    exclude: Optional[uuid.UUID] = None,
) -> int:
    """Messages of the campaign that left or may have left (accepted, in flight, unknown) since `since`. `exclude` is
    the message being decided right now: it is "in flight" because it was claimed, and must not count against itself."""
    stmt = select(func.count()).where(
        CampaignDispatch.account_id == account_id,
        CampaignDispatch.campaign_id == campaign_id,
        CampaignDispatch.status.in_(("accepted", "sending", "unknown")),
    )
    if since is not None:
        stmt = stmt.where(CampaignDispatch.last_checked_at >= since)  # when it was handled (= when it was sent)
    if exclude is not None:
        stmt = stmt.where(CampaignDispatch.id != exclude)
    return int((await session.execute(stmt)).scalar_one())
