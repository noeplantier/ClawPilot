"""Metering ledger (append-only) used by cost control."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Account, UsageRecord


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


# ---- Credits (services/outreach_os/credits.py): the spends of the last day and a half are enough for both windows ----
async def credit_spends(session: AsyncSession, account_id: uuid.UUID, since: datetime) -> list[tuple[datetime, int]]:
    rows = await session.execute(
        select(UsageRecord.created_at, UsageRecord.quantity).where(
            UsageRecord.account_id == account_id, UsageRecord.kind == "credits", UsageRecord.created_at >= since
        )
    )
    return [(at, int(n)) for at, n in rows.all()]


async def spend_credits(session: AsyncSession, account_id: uuid.UUID, amount: int, meta: dict) -> None:
    """Append one spend (never updated or deleted). Locks the account row first, so two spends of the same account are
    counted one after the other: the check before it and this write see the same total."""
    if amount <= 0:
        return
    await record(session, account_id, "credits", amount, meta)


async def lock_account(session: AsyncSession, account_id: uuid.UUID) -> None:
    await session.execute(select(Account.id).where(Account.id == account_id).with_for_update())


async def outreach_model(session: AsyncSession, account_id: uuid.UUID) -> Optional[str]:
    return (await session.execute(select(Account.outreach_model).where(Account.id == account_id))).scalar_one_or_none()


async def set_outreach_model(session: AsyncSession, account_id: uuid.UUID, model_id: str) -> None:
    await session.execute(update(Account).where(Account.id == account_id).values(outreach_model=model_id))
