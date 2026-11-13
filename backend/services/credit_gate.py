"""Credits, enforced: read the account's windows, refuse a spend that does not fit, record the ones that happened.

The rules are pure (`services/outreach_os/credits.py`); this module only reads and writes through `usage_repo`.
A spend is checked BEFORE the provider is called and recorded only once the provider answered: a failed call costs
nothing. The account row is locked during the check, so two requests of the same account are counted one after the
other.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from repositories import usage_repo
from services.outreach_os import credits


class CreditsExhausted(Exception):
    def __init__(self, refusal: credits.Refusal) -> None:
        super().__init__(refusal.message)
        self.refusal = refusal


class ModelWithoutAI(Exception):
    """The chosen model writes without AI: the AI composer and the AI drafts are not used."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def limits() -> credits.Limits:
    return credits.limits_from(dict(os.environ))


async def chosen_model(session: AsyncSession, account_id: uuid.UUID) -> credits.OutreachModel:
    return credits.model(await usage_repo.outreach_model(session, account_id))


async def windows(session: AsyncSession, account_id: uuid.UUID, now: datetime) -> list[credits.Window]:
    since = credits.day_start(now) - timedelta(hours=credits.SESSION_HOURS + 1)
    spends = await usage_repo.credit_spends(session, account_id, since)
    return credits.windows(spends, now, limits())


async def state(session: AsyncSession, account_id: uuid.UUID, now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    current = await chosen_model(session, account_id)
    return {
        "model": current.id,
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "tagline": m.tagline,
                "description": m.description,
                "credits": m.credits,
                "uses_ai": m.uses_ai,
                "max_words": m.max_words,
                "default": m.id == credits.DEFAULT_MODEL,
            }
            for m in credits.MODELS
        ],
        "windows": [w.as_dict() for w in await windows(session, account_id, now)],
        "settings": ["CREDITS_PER_DAY", "CREDITS_PER_SESSION"],  # names only, never a value of a secret
        "generated_at": now,
    }


async def reserve(
    session: AsyncSession, account_id: uuid.UUID, units: int = 1, now: Optional[datetime] = None
) -> tuple[credits.OutreachModel, int]:
    """The account's model and the cost of `units` messages, or CreditsExhausted / ModelWithoutAI. Records nothing."""
    now = now or utcnow()
    await usage_repo.lock_account(session, account_id)
    chosen = await chosen_model(session, account_id)
    if not chosen.uses_ai:
        raise ModelWithoutAI(chosen.name)
    cost = chosen.credits * max(1, units)
    refusal = credits.check(await windows(session, account_id, now), cost, now)
    if refusal is not None:
        raise CreditsExhausted(refusal)
    return chosen, cost


async def spent(
    session: AsyncSession, account_id: uuid.UUID, chosen: credits.OutreachModel, cost: int, action: str
) -> None:
    await usage_repo.spend_credits(session, account_id, cost, {"action": action, "model": chosen.id})
