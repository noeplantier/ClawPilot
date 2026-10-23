"""System health for operators: database, migrations, cache, jobs, and a live probe of the public OpenStreetMap servers.

Nothing secret is returned (database host kind and port only). The Overpass probe makes one polite status request per
server from the API host itself, so it answers the question "can this deployment reach them" with facts.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.config import Config
from alembic.script import ScriptDirectory
from db.session import get_db_session
from db.url import describe_database
from deps import get_current_user, require_roles
from repositories import map_job_repo
from services import feature_flags, map_job_runner, overpass_svc
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
    jobs: dict = {}
    try:
        await session.execute(text("SELECT 1"))
        database["ok"] = True
        database["latency_ms"] = int((time.monotonic() - started) * 1000)
        row = await session.execute(text("SELECT version_num FROM alembic_version"))
        migrations["current"] = row.scalar_one_or_none()
        migrations["ok"] = migrations["current"] is not None and migrations["current"] == migrations["head"]
        cache = {"ok": True, **await map_job_repo.cache_stats(session, now)}
        jobs = await map_job_repo.job_counts(session, now - timedelta(hours=24))
    except Exception:  # noqa: BLE001 (a broken dependency is the thing to show)
        await session.rollback()
    org = uuid.UUID(user["org_id"])
    return {
        "generated_at": now,
        "database": database,
        "migrations": migrations,
        "cache": cache,
        "map_jobs_24h": jobs,
        "workers": {
            "mode": "in_process",
            "note": "Map searches run as background tasks of the API process (no separate worker on this plan); the "
            "job row is the state, a lost job is reported as such.",
        },
        "overpass": {
            "endpoints": [e.split("//", 1)[1].split("/", 1)[0] for e in overpass_svc.endpoints()],
            "probe": "POST /api/system/health/overpass (owner/admin)",
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
    return {"ok": any(r["ok"] for r in results), "servers": results}
