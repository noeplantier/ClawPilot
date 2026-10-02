"""Per-organisation suppression list (opt-outs, erasure requests). Identities are stored as digests only."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SuppressionEntry
from services.outreach_os.normalize import identity_hash


async def add(session: AsyncSession, account_id: uuid.UUID, kind: str, value: str, *, reason: str) -> bool:
    """Idempotently suppress an already-normalised identity. Returns True if it was newly added."""
    stmt = (
        pg_insert(SuppressionEntry)
        .values(account_id=account_id, kind=kind, identity_hash=identity_hash(kind, value), reason=reason)
        .on_conflict_do_nothing(index_elements=["account_id", "kind", "identity_hash"])
        .returning(SuppressionEntry.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def is_suppressed(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    domain: Optional[str] = None,
) -> bool:
    pairs = [(k, identity_hash(k, v)) for k, v in (("email", email), ("phone", phone), ("domain", domain)) if v]
    if not pairs:
        return False
    result = await session.execute(
        select(SuppressionEntry.id)
        .where(SuppressionEntry.account_id == account_id, SuppressionEntry.identity_hash.in_([h for _, h in pairs]))
        .limit(1)
    )
    return result.first() is not None
