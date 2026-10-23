"""Map search jobs, their staged results and the source cache. Only this module touches these tables."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MapSearchJob, MapSearchResult, SourceCache
from services.outreach_os import map_jobs

RETENTION_DAYS = 30  # staged results are search results, not prospects: they do not outlive their usefulness
PLACE_FIELDS = (
    "external_id",
    "name",
    "category",
    "lat",
    "lon",
    "address",
    "postcode",
    "city",
    "phone",
    "email",
    "website",
    "source_url",
)


async def create_job(
    session: AsyncSession, account_id: uuid.UUID, user_id: Optional[uuid.UUID], box: map_jobs.Bbox, category: str
) -> MapSearchJob:
    job = MapSearchJob(
        account_id=account_id,
        created_by=user_id,
        category=category,
        south=box.south,
        west=box.west,
        north=box.north,
        east=box.east,
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(session: AsyncSession, account_id: uuid.UUID, job_id: uuid.UUID) -> Optional[MapSearchJob]:
    return (
        await session.execute(
            select(MapSearchJob).where(MapSearchJob.id == job_id, MapSearchJob.account_id == account_id)
        )
    ).scalar_one_or_none()


async def get_job_any(session: AsyncSession, job_id: uuid.UUID) -> Optional[MapSearchJob]:
    """For the runner only (it works from a job id it created itself)."""
    return (await session.execute(select(MapSearchJob).where(MapSearchJob.id == job_id))).scalar_one_or_none()


async def list_jobs(session: AsyncSession, account_id: uuid.UUID, limit: int = 10) -> list[MapSearchJob]:
    rows = await session.execute(
        select(MapSearchJob)
        .where(MapSearchJob.account_id == account_id)
        .order_by(MapSearchJob.created_at.desc(), MapSearchJob.id)
        .limit(limit)
    )
    return list(rows.scalars())


async def fail_if_stale(session: AsyncSession, job: MapSearchJob, now: datetime) -> bool:
    """A job still queued/running long after it started was lost with its instance: say so, do not spin forever."""
    if job.status not in ("queued", "running"):
        return False
    started = job.started_at or job.created_at
    if (now - started).total_seconds() < map_jobs.JOB_STALE_SECONDS:
        return False
    await mark_failed(session, job, "job_lost", map_jobs.HINTS["job_lost"], now, None)
    return True


async def mark_running(session: AsyncSession, job: MapSearchJob, now: datetime) -> None:
    job.status = "running"
    job.started_at = now
    await session.flush()


async def mark_failed(
    session: AsyncSession, job: MapSearchJob, code: str, message: str, now: datetime, duration_ms: Optional[int]
) -> None:
    job.status = "failed"
    job.error_code = code
    job.error = message[:1000]
    job.finished_at = now
    job.duration_ms = duration_ms
    await session.flush()


async def mark_succeeded(
    session: AsyncSession,
    job: MapSearchJob,
    *,
    source: str,
    count: int,
    truncated: bool,
    cache_hit: bool,
    now: datetime,
    duration_ms: int,
) -> None:
    job.status = "succeeded"
    job.source = source
    job.result_count = count
    job.truncated = truncated
    job.cache_hit = cache_hit
    job.error_code = None
    job.error = None
    job.finished_at = now
    job.duration_ms = duration_ms
    await session.flush()


async def save_results(
    session: AsyncSession,
    account_id: uuid.UUID,
    job_id: uuid.UUID,
    places: list[dict[str, Any]],
    collected_at: datetime,
) -> int:
    """Insert the places of a job; a place already staged for this job (same dedupe key) is left as it is."""
    if not places:
        return 0
    values = [
        {
            "account_id": account_id,
            "job_id": job_id,
            "dedupe_key": p["dedupe_key"],
            "source_type": "openstreetmap",
            "collected_at": collected_at,
            **{k: p.get(k) for k in PLACE_FIELDS},
        }
        for p in places
    ]
    stmt = pg_insert(MapSearchResult).values(values).on_conflict_do_nothing(index_elements=["job_id", "dedupe_key"])
    await session.execute(stmt)
    count = await session.execute(
        select(func.count()).select_from(MapSearchResult).where(MapSearchResult.job_id == job_id)
    )
    return int(count.scalar_one())


async def list_results(session: AsyncSession, account_id: uuid.UUID, job_id: uuid.UUID) -> list[MapSearchResult]:
    rows = await session.execute(
        select(MapSearchResult)
        .where(MapSearchResult.job_id == job_id, MapSearchResult.account_id == account_id)
        .order_by(MapSearchResult.name, MapSearchResult.id)
    )
    return list(rows.scalars())


async def purge_old(session: AsyncSession, account_id: uuid.UUID, now: datetime) -> int:
    """Delete this organisation's jobs (and, by cascade, their staged results) older than the retention."""
    cutoff = now - timedelta(days=RETENTION_DAYS)
    result = await session.execute(
        delete(MapSearchJob).where(MapSearchJob.account_id == account_id, MapSearchJob.created_at < cutoff)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


# ----------------------------------------------------------------- source cache
async def cache_get(session: AsyncSession, key: str, now: datetime) -> Optional[dict[str, Any]]:
    row = (
        await session.execute(select(SourceCache).where(SourceCache.key == key, SourceCache.expires_at > now))
    ).scalar_one_or_none()
    return dict(row.payload) if row else None


async def cache_put(session: AsyncSession, key: str, payload: dict[str, Any], now: datetime) -> None:
    expires = now + timedelta(seconds=map_jobs.CACHE_TTL_SECONDS)
    stmt = pg_insert(SourceCache).values(key=key, payload=payload, created_at=now, expires_at=expires)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"], set_={"payload": payload, "created_at": now, "expires_at": expires}
    )
    await session.execute(stmt)


async def cache_stats(session: AsyncSession, now: datetime) -> dict[str, int]:
    live = (
        await session.execute(select(func.count()).select_from(SourceCache).where(SourceCache.expires_at > now))
    ).scalar_one()
    return {"live_entries": int(live)}


async def cache_purge_expired(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(delete(SourceCache).where(SourceCache.expires_at <= now))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def job_counts(session: AsyncSession, since: datetime) -> dict[str, int]:
    rows = await session.execute(
        select(MapSearchJob.status, func.count()).where(MapSearchJob.created_at >= since).group_by(MapSearchJob.status)
    )
    return {status: int(n) for status, n in rows.all()}
