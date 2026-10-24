"""System health for operators: database, migrations, cache, jobs, and a live probe of the public OpenStreetMap servers.

Nothing secret is returned (database host kind and port only). The Overpass probe makes one polite status request per
server from the API host itself, so it answers the question "can this deployment reach them" with facts.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.config import Config
from alembic.script import ScriptDirectory
from db.models import Account, JobRun, PublicPageCache, UsageRecord
from db.session import get_db_session
from db.url import describe_database
from deps import get_current_user, require_roles
from repositories import map_job_repo
from services import ai_svc, celery_health, feature_flags, imap_svc, map_job_runner, overpass_svc, smtp_svc
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/system", tags=["system"])
decider = require_roles("owner", "admin")
_probe_limiter = AttemptLimiter(3, 60.0)
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _script_head() -> str | None:
    try:
        heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()
    except Exception:  # noqa: BLE001 (health must report, not raise)
        return None
    return heads[0] if len(heads) == 1 else None


@router.get("/health")
async def health(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    now = map_job_runner.utcnow()
    started = time.monotonic()
    database: dict[str, Any] = {**describe_database(), "ok": False, "latency_ms": None}
    migrations: dict = {"ok": False, "current": None, "head": _script_head()}
    cache: dict = {"ok": False}
    map_jobs: dict = {}
    recent_jobs = []
    job_counts: dict = {}
    quotas: dict = {}
    page_cache: dict = {"ok": False, "entries": None}
    try:
        await session.execute(text("SELECT 1"))
        database["ok"] = True
        database["latency_ms"] = int((time.monotonic() - started) * 1000)
        row = await session.execute(text("SELECT version_num FROM alembic_version"))
        migrations["current"] = row.scalar_one_or_none()
        migrations["ok"] = migrations["current"] is not None and migrations["current"] == migrations["head"]
        cache = {"ok": True, **await map_job_repo.cache_stats(session, now)}
        map_jobs = await map_job_repo.job_counts(session, now - timedelta(hours=24))
        page_cache_count = await session.scalar(
            select(func.count()).select_from(PublicPageCache).where(PublicPageCache.expires_at > now)
        )
        page_cache = {"ok": True, "live_entries": int(page_cache_count or 0), "checked_at": now}
        account_id = uuid.UUID(user["org_id"])
        counts = await session.execute(
            select(JobRun.status, func.count())
            .where(JobRun.account_id == account_id, JobRun.created_at >= now - timedelta(hours=24))
            .group_by(JobRun.status)
        )
        job_counts = {status: count for status, count in counts.all()}
        jobs = await session.execute(
            select(JobRun).where(JobRun.account_id == account_id).order_by(JobRun.created_at.desc()).limit(10)
        )
        recent_jobs = [
            {
                "id": str(job.id),
                "job_type": job.job_type,
                "status": job.status,
                "total_items": job.total_items,
                "processed_items": job.processed_items,
                "failed_items": job.failed_items,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
                "error": job.error,
            }
            for job in jobs.scalars()
        ]
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        usage = await session.execute(
            select(UsageRecord.kind, func.sum(UsageRecord.quantity))
            .where(UsageRecord.account_id == account_id, UsageRecord.created_at >= month_start)
            .group_by(UsageRecord.kind)
        )
        plan = await session.scalar(select(Account.plan).where(Account.id == account_id))
        quotas = {
            "plan": plan,
            "period_started_at": month_start,
            "consumed": {kind: int(quantity or 0) for kind, quantity in usage.all()},
            "limits_configured": False,
            "checked_at": now,
        }
    except Exception:  # noqa: BLE001 (a broken dependency is the thing to show)
        await session.rollback()
    org = uuid.UUID(user["org_id"])
    celery = await asyncio.to_thread(celery_health.snapshot, now)
    ai_config = ai_svc.config()
    return {
        "generated_at": now,
        "database": database,
        "migrations": migrations,
        "cache": cache,
        "public_page_cache": page_cache,
        "map_jobs_24h": map_jobs,
        "jobs_24h": job_counts,
        "recent_jobs": recent_jobs,
        "workers": celery["worker"],
        "beat": celery["beat"],
        "automation_queue": {**celery["automation_queue"], "broker_ok": celery["broker_ok"]},
        "integrations": {
            "overpass": {"status": "not_checked", "checked_at": None},
            "smtp": {"status": "configured" if smtp_svc.is_configured() else "not_configured", "checked_at": now},
            "imap": {"status": "configured" if imap_svc.is_configured() else "not_configured", "checked_at": now},
            "groq": {
                "status": "configured" if ai_config is not None and ai_config.provider == "groq" else "not_configured",
                "checked_at": now,
                "probe_performed": False,
            },
        },
        "quotas": quotas,
        "overpass": {
            "endpoints": [e.split("//", 1)[1].split("/", 1)[0] for e in overpass_svc.endpoints()],
            "cooling_down": overpass_svc.cooling_hosts(),
            "status": "not_checked",
            "checked_at": None,
        },
        "flags": {
            "external_sources": feature_flags.is_enabled("external_sources"),
            "prospect_import": feature_flags.is_enabled("prospect_import"),
        },
        "limits": {"searches_per_minute": 6, "organisation": str(org)},
    }


@router.post("/health/overpass")
async def probe_overpass(user: dict = Depends(decider)):
    key = str(uuid.UUID(user["org_id"]))
    wait = _probe_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Probe limit reached: wait a minute", headers={"Retry-After": str(wait)}
        )
    _probe_limiter.record(key)
    results = []
    for endpoint in overpass_svc.endpoints():  # one after the other: never a burst on public servers
        results.append(await asyncio.to_thread(overpass_svc.probe, endpoint))
    return {"ok": any(r["ok"] for r in results), "servers": results, "checked_at": datetime.now(timezone.utc)}
