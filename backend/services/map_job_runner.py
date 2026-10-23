"""Runs map search jobs: cache first, then one polite Overpass request, normalise, de-duplicate, persist, report.

The route creates the job (status queued) and returns at once; `schedule_job` starts `execute` in the background. The
job row is the only state: a restart mid-job leaves it queued/running and `fail_if_stale` reports it as lost.
Network calls are serialised process-wide (one Overpass request at a time) and cached in `source_cache` for a few hours.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import MapSearchJob
from db.session import AsyncSessionLocal
from repositories import map_job_repo
from services import overpass_svc
from services.outreach_os import map_jobs, osm
from services.outreach_os.types import RawListing

logger = logging.getLogger(__name__)
_NETWORK_GATE = threading.Semaphore(1)
_background: set[asyncio.Task[None]] = set()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def place_of(item: RawListing) -> dict[str, Any]:
    return {
        "dedupe_key": map_jobs.dedupe_key(item),
        "external_id": item.external_id,
        "name": item.name,
        "category": item.category,
        "lat": item.lat or 0.0,
        "lon": item.lon or 0.0,
        "address": item.address,
        "postcode": item.postcode,
        "city": item.city,
        "phone": item.phone,
        "email": item.email,
        "website": item.website,
        "source_url": item.source_url,
    }


def box_of(job: MapSearchJob) -> map_jobs.Bbox:
    return map_jobs.Bbox(job.south, job.west, job.north, job.east)


def query_for(box: map_jobs.Bbox, category: str) -> str:
    """The Overpass query for the snapped area (raises osm.BadArea when the snapped area is too large)."""
    snapped = map_jobs.snap_bbox(box)
    return osm.build_query(snapped.south, snapped.west, snapped.north, snapped.east, category)


def places_from(data: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    listings = map_jobs.dedupe(osm.parse_elements(data))
    elements = data.get("elements", [])
    return [place_of(item) for item in listings], len(elements) >= osm.MAX_RESULTS


def _gated(fetcher: Callable[[str], dict[str, Any]], query: str) -> dict[str, Any]:
    with _NETWORK_GATE:
        return fetcher(query)


def _log(job_id: uuid.UUID, account_id: uuid.UUID, status: str, started: float, **extra: Any) -> None:
    fields = " ".join(f"{k}={v}" for k, v in extra.items())
    logger.info(
        "map_job job_id=%s workspace_id=%s status=%s duration_ms=%d %s",
        job_id,
        account_id,
        status,
        int((time.monotonic() - started) * 1000),
        fields,
    )


async def persist_success(
    session: AsyncSession,
    job: MapSearchJob,
    places: list[dict[str, Any]],
    truncated: bool,
    *,
    source: str,
    cache_hit: bool,
    now: datetime,
    started: float,
) -> None:
    count = await map_job_repo.save_results(session, job.account_id, job.id, places, now)
    await map_job_repo.mark_succeeded(
        session,
        job,
        source=source,
        count=count,
        truncated=truncated,
        cache_hit=cache_hit,
        now=now,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def execute(
    job_id: uuid.UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
    now: Callable[[], datetime] = utcnow,
) -> None:
    started = time.monotonic()
    fetch = fetcher or overpass_svc.default_fetcher
    async with session_factory() as session:
        job = await map_job_repo.get_job_any(session, job_id)
        if job is None or job.status != "queued":
            return
        await map_job_repo.mark_running(session, job, now())
        await session.commit()
        account_id, category, box = job.account_id, job.category, box_of(job)
    key = map_jobs.cache_key(box, category)

    async def fail(code: str, message: str) -> None:
        async with session_factory() as s:
            row = await map_job_repo.get_job_any(s, job_id)
            if row is not None:
                await map_job_repo.mark_failed(s, row, code, message, now(), int((time.monotonic() - started) * 1000))
            await s.commit()
        _log(job_id, account_id, "failed", started, error_code=code)

    try:
        async with session_factory() as s:
            cached = await map_job_repo.cache_get(s, key, now())
        if cached is not None:
            places, truncated, source = cached["places"], bool(cached.get("truncated")), "cache"
        else:
            data = await asyncio.to_thread(_gated, fetch, query_for(box, category))
            if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
                raise overpass_svc.Unavailable("not an Overpass answer", code="overpass_bad_answer")
            places, truncated = places_from(data)
            source = "overpass"
    except overpass_svc.Unavailable as exc:
        detail = "; ".join(exc.failures)
        base = map_jobs.HINTS.get(exc.code, str(exc))
        await fail(exc.code, f"{base} ({detail})" if detail else base)
        return
    except Exception:  # noqa: BLE001 (any other failure must end the job, never leave it running)
        logger.exception("map_job job_id=%s internal error", job_id)
        await fail("internal_error", map_jobs.HINTS["internal_error"])
        return

    async with session_factory() as s:
        row = await map_job_repo.get_job_any(s, job_id)
        if row is None:
            return
        stamp = now()
        await persist_success(
            s, row, places, truncated, source=source, cache_hit=source == "cache", now=stamp, started=started
        )
        if source == "overpass":
            await map_job_repo.cache_put(s, key, {"places": places, "truncated": truncated}, stamp)
        await s.commit()
    _log(job_id, account_id, "succeeded", started, source=source, results=len(places))


def schedule_job(job_id: uuid.UUID) -> None:
    """Start the job in the background of the running event loop (replaced by a no-op in tests)."""
    task = asyncio.get_running_loop().create_task(execute(job_id))
    _background.add(task)
    task.add_done_callback(_background.discard)
