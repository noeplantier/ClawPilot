"""CRM notes — free-text, attached to a lead and/or a campaign."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Note

ACTIVE = Note.deleted_at.is_(None)


async def create_note(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    author_user_id: uuid.UUID,
    body: str,
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> Note:
    note = Note(
        account_id=account_id,
        author_user_id=author_user_id,
        body=body,
        lead_id=uuid.UUID(lead_id) if lead_id else None,
        campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
    )
    session.add(note)
    await session.flush()
    return note


async def list_notes(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> list[Note]:
    stmt = select(Note).where(Note.account_id == account_id, ACTIVE)
    if lead_id:
        stmt = stmt.where(Note.lead_id == uuid.UUID(lead_id))
    if campaign_id:
        stmt = stmt.where(Note.campaign_id == uuid.UUID(campaign_id))
    result = await session.execute(stmt.order_by(Note.created_at.desc()))
    return list(result.scalars().all())


async def delete_note(session: AsyncSession, account_id: uuid.UUID, note_id: str) -> bool:
    try:
        nid = uuid.UUID(note_id)
    except ValueError:
        return False
    result = await session.execute(select(Note).where(Note.id == nid, Note.account_id == account_id, ACTIVE))
    note = result.scalar_one_or_none()
    if not note:
        return False
    note.deleted_at = func.now()
    return True
