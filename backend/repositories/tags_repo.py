"""Tags-as-entities (name + color, many-to-many with leads via `lead_tags`).

`Lead.tags` (a plain string array) stays as the fast denormalized read-cache
already relied on for filtering/scoring (services/scoring.py, tasks/
automation_tasks.py read it directly) — this repo owns the tag *catalog* and
keeps that cache in sync on attach/detach, the same pattern already used for
`Lead.score` against the `lead_scores` history.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead, LeadTag, Tag

LEAD_ACTIVE = Lead.deleted_at.is_(None)


async def list_tags(session: AsyncSession, account_id: uuid.UUID) -> list[Tag]:
    result = await session.execute(select(Tag).where(Tag.account_id == account_id).order_by(Tag.name))
    return list(result.scalars().all())


async def get_tag_by_name(session: AsyncSession, account_id: uuid.UUID, name: str) -> Optional[Tag]:
    result = await session.execute(select(Tag).where(Tag.account_id == account_id, Tag.name == name))
    return result.scalar_one_or_none()


async def create_tag(session: AsyncSession, account_id: uuid.UUID, *, name: str, color: Optional[str] = None) -> Tag:
    tag = Tag(account_id=account_id, name=name, color=color)
    session.add(tag)
    await session.flush()
    return tag


async def _get_tag(session: AsyncSession, account_id: uuid.UUID, tag_id: str) -> Optional[Tag]:
    try:
        tid = uuid.UUID(tag_id)
    except ValueError:
        return None
    result = await session.execute(select(Tag).where(Tag.id == tid, Tag.account_id == account_id))
    return result.scalar_one_or_none()


async def _get_lead(session: AsyncSession, account_id: uuid.UUID, lead_id: str) -> Optional[Lead]:
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        return None
    result = await session.execute(select(Lead).where(Lead.id == lid, Lead.account_id == account_id, LEAD_ACTIVE))
    return result.scalar_one_or_none()


async def delete_tag(session: AsyncSession, account_id: uuid.UUID, tag_id: str) -> bool:
    tag = await _get_tag(session, account_id, tag_id)
    if not tag:
        return False
    # Drop the denormalized name from every lead currently carrying it.
    leads_result = await session.execute(
        select(Lead).where(Lead.account_id == account_id, Lead.tags.contains([tag.name]))
    )
    for lead in leads_result.scalars().all():
        lead.tags = [t for t in lead.tags if t != tag.name]
    await session.delete(tag)
    await session.flush()
    return True


async def attach_tag(session: AsyncSession, account_id: uuid.UUID, lead_id: str, tag_id: str) -> Optional[Lead]:
    lead = await _get_lead(session, account_id, lead_id)
    tag = await _get_tag(session, account_id, tag_id)
    if not lead or not tag:
        return None

    existing = await session.execute(select(LeadTag).where(LeadTag.lead_id == lead.id, LeadTag.tag_id == tag.id))
    if not existing.scalar_one_or_none():
        session.add(LeadTag(lead_id=lead.id, tag_id=tag.id))
        if tag.name not in lead.tags:
            lead.tags = sorted(set(lead.tags) | {tag.name})
        await session.flush()
    return lead


async def detach_tag(session: AsyncSession, account_id: uuid.UUID, lead_id: str, tag_id: str) -> Optional[Lead]:
    lead = await _get_lead(session, account_id, lead_id)
    tag = await _get_tag(session, account_id, tag_id)
    if not lead or not tag:
        return None

    link_result = await session.execute(select(LeadTag).where(LeadTag.lead_id == lead.id, LeadTag.tag_id == tag.id))
    link = link_result.scalar_one_or_none()
    if link:
        await session.delete(link)
        lead.tags = [t for t in lead.tags if t != tag.name]
        await session.flush()
    return lead
