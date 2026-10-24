"""Metering ledger (append-only) used by cost control."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UsageRecord


async def record(
    session: AsyncSession, account_id: uuid.UUID, kind: str, quantity: int, meta: Optional[dict] = None
) -> None:
    session.add(UsageRecord(account_id=account_id, kind=kind, quantity=quantity, meta=meta or {}))
    await session.flush()


async def totals(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    rows = await session.execute(
        select(UsageRecord.kind, func.coalesce(func.sum(UsageRecord.quantity), 0))
        .where(UsageRecord.account_id == account_id)
        .group_by(UsageRecord.kind)
    )
    return {kind: int(total) for kind, total in rows.all()}
