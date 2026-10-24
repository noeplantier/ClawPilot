"""Imported prospect lists: one append-only row per batch (origin, legal basis, file hash, outcome)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ProspectImportBatch


async def create(session: AsyncSession, account_id: uuid.UUID, **fields: object) -> ProspectImportBatch:
    batch = ProspectImportBatch(account_id=account_id, **fields)
    session.add(batch)
    await session.flush()
    return batch


async def list_batches(session: AsyncSession, account_id: uuid.UUID, *, limit: int = 50) -> list[ProspectImportBatch]:
    rows = await session.execute(
        select(ProspectImportBatch)
        .where(ProspectImportBatch.account_id == account_id)
        .order_by(ProspectImportBatch.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars())


async def get_by_hash(
    session: AsyncSession, account_id: uuid.UUID, content_sha256: str
) -> Optional[ProspectImportBatch]:
    """An earlier batch with the same file content, if any (to warn about a re-import)."""
    return (
        await session.execute(
            select(ProspectImportBatch)
            .where(ProspectImportBatch.account_id == account_id, ProspectImportBatch.content_sha256 == content_sha256)
            .limit(1)
        )
    ).scalar_one_or_none()
