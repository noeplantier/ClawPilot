"""Automatic AI draft jobs: which eligible prospects still need a draft, their state, and the batch-panel summary.

Only this module (and the runner that uses it) writes `draft_jobs`. A job never touches a prospect's visibility."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Collection, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Account, DraftJob, Lead
from db.models.prospect import DRAFT_JOB_STATUSES
from repositories import eligibility_sql, heat_sql
from repositories.prospect_repo import ACTIVE, IN_DISCOVERY

RETRY_AFTER_SECONDS = {"unavailable": 300, "failed": 120}  # a provider limit or error is asked again later, not at once
STALE_GENERATING_SECONDS = 300  # a job left "generating" by a restart is taken again
MAX_ATTEMPTS = 3


async def offer_of(session: AsyncSession, account_id: uuid.UUID) -> Optional[dict]:
    return (await session.execute(select(Account.offer).where(Account.id == account_id))).scalar_one_or_none()


async def set_offer(session: AsyncSession, account_id: uuid.UUID, offer: Optional[dict]) -> None:
    await session.execute(update(Account).where(Account.id == account_id).values(offer=offer))


async def candidates(
    session: AsyncSession,
    account_id: uuid.UUID,
    offer: str,
    limit: int,
    now: Optional[datetime] = None,
    only: Optional[Collection[uuid.UUID]] = None,
) -> list[uuid.UUID]:
    """Qualified prospects that have no job for this offer yet, or changed since their last job. Hot ones first.
    Whether the *data* really changed is decided by the idempotency key (the same key never prepares a second draft).
    `only` restricts the search to those prospects (the recipients of one campaign)."""
    src = eligibility_sql.latest_source(account_id)
    latest = (
        select(
            DraftJob.lead_id.label("lead_id"), DraftJob.offer_hash.label("offer_hash"), DraftJob.created_at.label("at")
        )
        .where(DraftJob.account_id == account_id)
        .distinct(DraftJob.lead_id)
        .order_by(DraftJob.lead_id, DraftJob.created_at.desc())
        .subquery("latest_job")
    )
    scores = heat_sql.latest_scores()
    scope = [Lead.id.in_(list(only))] if only is not None else []
    rows = await session.execute(
        select(Lead.id)
        .join(src, src.c.lead_id == Lead.id)
        .outerjoin(latest, latest.c.lead_id == Lead.id)
        .outerjoin(scores, scores.c.lead_id == Lead.id)
        .where(
            Lead.account_id == account_id,
            ACTIVE,
            IN_DISCOVERY,
            eligibility_sql.qualified(src, now),
            or_(latest.c.lead_id.is_(None), latest.c.offer_hash != offer, Lead.updated_at > latest.c.at),
            *scope,
        )
        .order_by(
            eligibility_sql.hot(src, now).desc(),
            heat_sql.heat_sql(scores.c.score).desc(),
            Lead.created_at.desc(),
            Lead.id,
        )
        .limit(limit)
    )
    return list(rows.scalars())


async def create(
    session: AsyncSession,
    account_id: uuid.UUID,
    lead_id: uuid.UUID,
    *,
    key: str,
    offer: str,
    language: str,
    site_state: str,
    status: str,
) -> bool:
    """One job per idempotency key. True when created, False when the key already exists (nothing is redone)."""
    stmt = (
        pg_insert(DraftJob)
        .values(
            account_id=account_id,
            lead_id=lead_id,
            idempotency_key=key,
            offer_hash=offer,
            language=language,
            site_state=site_state,
            status=status,
            error_code="offer_required" if status == "offer_required" else None,
            error=(
                "Configure your offer (Pilotage > Offer) to get a draft for this prospect."
                if status == "offer_required"
                else None
            ),
        )
        .on_conflict_do_nothing(index_elements=["account_id", "idempotency_key"])
        .returning(DraftJob.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def due(
    session: AsyncSession,
    account_id: uuid.UUID,
    limit: int,
    now: datetime,
    only: Optional[Collection[uuid.UUID]] = None,
) -> list[uuid.UUID]:
    """Jobs to run now: queued ones, failed/unavailable ones whose wait is over, and ones a restart left generating.
    `only` restricts them to the jobs of those prospects."""
    retry = [
        (DraftJob.status == status)
        & (DraftJob.updated_at <= now - timedelta(seconds=wait))
        & (DraftJob.attempts < MAX_ATTEMPTS)
        for status, wait in RETRY_AFTER_SECONDS.items()
    ]
    stale = (DraftJob.status == "generating") & (
        DraftJob.updated_at <= now - timedelta(seconds=STALE_GENERATING_SECONDS)
    )
    rows = await session.execute(
        select(DraftJob.id)
        .where(
            DraftJob.account_id == account_id,
            or_(DraftJob.status == "queued", stale, *retry),
            *([DraftJob.lead_id.in_(list(only))] if only is not None else []),
        )
        .order_by(DraftJob.created_at, DraftJob.id)
        .limit(limit)
    )
    return list(rows.scalars())


async def claim(session: AsyncSession, job_id: uuid.UUID, now: datetime) -> Optional[DraftJob]:
    """Lock a job and mark it generating (another sweep skips it); None when it is gone or already taken."""
    job = (
        await session.execute(select(DraftJob).where(DraftJob.id == job_id).with_for_update(skip_locked=True))
    ).scalar_one_or_none()
    if job is None or job.status in ("ready", "offer_required"):
        return None
    job.status = "generating"
    job.attempts += 1
    job.started_at = now
    job.finished_at = None
    await session.flush()
    return job


async def finish(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    status: str,
    now: datetime,
    draft_id: Optional[uuid.UUID] = None,
    error_code: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    job = await session.get(DraftJob, job_id)
    if job is None:
        return
    job.status = status
    job.finished_at = now
    job.draft_id = draft_id
    job.error_code = error_code
    job.error = error[:400] if error else None
    await session.flush()


async def latest_for_lead(session: AsyncSession, account_id: uuid.UUID, lead_id: uuid.UUID) -> Optional[DraftJob]:
    return (
        await session.execute(
            select(DraftJob)
            .where(DraftJob.account_id == account_id, DraftJob.lead_id == lead_id)
            .order_by(DraftJob.created_at.desc(), DraftJob.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def summary(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    """Prospects by the state of their latest job (every state present, zero when none): what a batch panel shows."""
    latest = (
        select(DraftJob.status.label("status"))
        .where(DraftJob.account_id == account_id)
        .distinct(DraftJob.lead_id)
        .order_by(DraftJob.lead_id, DraftJob.created_at.desc())
        .subquery()
    )
    rows = await session.execute(select(latest.c.status, func.count()).group_by(latest.c.status))
    counts = dict.fromkeys(DRAFT_JOB_STATUSES, 0)
    counts.update({status: int(n) for status, n in rows.all()})
    return counts
