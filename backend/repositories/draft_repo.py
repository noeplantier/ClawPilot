"""Message drafts: idempotent creation and human review state."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MessageDraft


async def create_idempotent(
    session: AsyncSession, account_id: uuid.UUID, *, idempotency_key: str, **fields: object
) -> tuple[MessageDraft, bool]:
    """Insert a draft, or return the existing one for the same key. Second item: True if newly created."""
    stmt = (
        pg_insert(MessageDraft)
        .values(account_id=account_id, idempotency_key=idempotency_key, **fields)
        .on_conflict_do_nothing(index_elements=["account_id", "idempotency_key"])
        .returning(MessageDraft.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    draft = (
        await session.execute(
            select(MessageDraft).where(
                MessageDraft.account_id == account_id, MessageDraft.idempotency_key == idempotency_key
            )
        )
    ).scalar_one()
    return draft, new_id is not None


async def get(session: AsyncSession, account_id: uuid.UUID, draft_id: str) -> Optional[MessageDraft]:
    try:
        did = uuid.UUID(draft_id)
    except ValueError:
        return None
    return (
        await session.execute(select(MessageDraft).where(MessageDraft.id == did, MessageDraft.account_id == account_id))
    ).scalar_one_or_none()


async def list_for_lead(session: AsyncSession, account_id: uuid.UUID, lead_id: uuid.UUID) -> list[MessageDraft]:
    result = await session.execute(
        select(MessageDraft)
        .where(MessageDraft.account_id == account_id, MessageDraft.lead_id == lead_id)
        .order_by(MessageDraft.created_at.desc())
    )
    return list(result.scalars())


async def review(
    session: AsyncSession, draft: MessageDraft, *, status: str, user_id: uuid.UUID, note: Optional[str]
) -> MessageDraft:
    draft.status = status
    draft.reviewed_by_user_id = user_id
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.review_note = note
    await session.flush()
    return draft
