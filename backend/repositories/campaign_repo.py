"""Campaign persistence — campaigns + campaign_steps + campaign_leads.

Replaces the legacy embedded-JSON `Campaign.steps`/`Campaign.lead_ids` with real
relational rows (plan doc section 1.8-1.10), while keeping the exact same HTTP
contract (`steps`/`lead_ids` as plain lists on the Campaign response).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Campaign, CampaignLead, CampaignStep

ACTIVE = Campaign.deleted_at.is_(None)
_OPTS = (selectinload(Campaign.steps), selectinload(Campaign.leads))


async def _set_steps(session: AsyncSession, campaign: Campaign, steps: list[dict]) -> None:
    for step in list(campaign.steps):
        await session.delete(step)
    await session.flush()
    campaign.steps = [
        CampaignStep(
            step_index=idx,
            channel=s.get("channel", "email"),
            delay_hours=s.get("delay_hours", 0),
            subject=s.get("subject"),
            body=s.get("body", ""),
            language=s.get("language", "en"),
        )
        for idx, s in enumerate(steps)
    ]


async def _set_leads(session: AsyncSession, campaign: Campaign, lead_ids: list[str]) -> None:
    for cl in list(campaign.leads):
        await session.delete(cl)
    await session.flush()
    campaign.leads = [CampaignLead(lead_id=uuid.UUID(lid)) for lid in lead_ids]


async def list_campaigns(session: AsyncSession, account_id: uuid.UUID) -> list[Campaign]:
    result = await session.execute(
        select(Campaign)
        .options(*_OPTS)
        .where(Campaign.account_id == account_id, ACTIVE)
        .order_by(Campaign.created_at.desc())
    )
    return list(result.unique().scalars().all())


async def create_campaign(session: AsyncSession, account_id: uuid.UUID, data: dict) -> Campaign:
    steps = data.pop("steps", []) or []
    lead_ids = data.pop("lead_ids", []) or []
    agent_id = data.pop("agent_id", None)
    campaign = Campaign(account_id=account_id, agent_id=uuid.UUID(agent_id) if agent_id else None, **data)
    campaign.steps = [
        CampaignStep(
            step_index=idx,
            channel=s.get("channel", "email"),
            delay_hours=s.get("delay_hours", 0),
            subject=s.get("subject"),
            body=s.get("body", ""),
            language=s.get("language", "en"),
        )
        for idx, s in enumerate(steps)
    ]
    campaign.leads = [CampaignLead(lead_id=uuid.UUID(lid)) for lid in lead_ids]
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign, attribute_names=["steps", "leads"])
    return campaign


async def get_campaign(session: AsyncSession, account_id: uuid.UUID, campaign_id: str) -> Optional[Campaign]:
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        return None
    result = await session.execute(
        select(Campaign).options(*_OPTS).where(Campaign.id == cid, Campaign.account_id == account_id, ACTIVE)
    )
    return result.unique().scalar_one_or_none()


async def update_campaign(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: str, updates: dict
) -> Optional[Campaign]:
    campaign = await get_campaign(session, account_id, campaign_id)
    if not campaign:
        return None
    if "steps" in updates:
        await _set_steps(session, campaign, updates.pop("steps") or [])
    if "lead_ids" in updates:
        await _set_leads(session, campaign, updates.pop("lead_ids") or [])
    if "agent_id" in updates:
        agent_id = updates.pop("agent_id")
        campaign.agent_id = uuid.UUID(agent_id) if agent_id else None
    for key, value in updates.items():
        setattr(campaign, key, value)
    await session.flush()
    await session.refresh(campaign, attribute_names=["steps", "leads"])
    return campaign


async def delete_campaign(session: AsyncSession, account_id: uuid.UUID, campaign_id: str) -> bool:
    from sqlalchemy import func

    campaign = await get_campaign(session, account_id, campaign_id)
    if not campaign:
        return False
    campaign.deleted_at = func.now()
    return True


async def assign_leads(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: str, lead_ids: list[str]
) -> Optional[Campaign]:
    campaign = await get_campaign(session, account_id, campaign_id)
    if not campaign:
        return None
    existing = {str(cl.lead_id) for cl in campaign.leads}
    for lid in lead_ids:
        if lid not in existing:
            campaign.leads.append(CampaignLead(lead_id=uuid.UUID(lid)))
            existing.add(lid)
    await session.flush()
    await session.refresh(campaign, attribute_names=["steps", "leads"])
    return campaign


async def aggregate_totals(session: AsyncSession, account_id: uuid.UUID) -> dict:
    from sqlalchemy import func

    result = await session.execute(
        select(
            func.coalesce(func.sum(Campaign.sent), 0),
            func.coalesce(func.sum(Campaign.opened), 0),
            func.coalesce(func.sum(Campaign.replied), 0),
            func.coalesce(func.sum(Campaign.converted), 0),
            func.count(),
        ).where(Campaign.account_id == account_id, ACTIVE)
    )
    sent, opened, replied, converted, count = result.one()
    return {"sent": sent, "opened": opened, "replied": replied, "converted": converted, "count": count}


async def increment_counters(
    session: AsyncSession,
    account_id: uuid.UUID,
    campaign_id: str,
    *,
    sent: int = 0,
    opened: int = 0,
    replied: int = 0,
    converted: int = 0,
    set_status: Optional[str] = None,
) -> None:
    campaign = await get_campaign(session, account_id, campaign_id)
    if not campaign:
        return
    campaign.sent += sent
    campaign.opened += opened
    campaign.replied += replied
    campaign.converted += converted
    if set_status:
        campaign.status = set_status
