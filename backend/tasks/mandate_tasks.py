"""Scheduled visit of the active mandates of the bounded automatic mode (services/mandate.py).

Does nothing unless FEATURE_AUTOMATION_MAX is on AND a mandate is active. Replies are only considered "read" when the
worker recorded a recent successful inbox poll (services/inbox_health.py)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery_app import celery_app
from services import feature_flags, imap_svc, inbox_health, mandate
from tasks._bridge import run_async

logger = logging.getLogger("outreachos.mandate")


async def _run(_session) -> dict:
    if not mandate.enabled():
        return {"status": "disabled"}
    from tasks._bridge import _SessionLocal  # the worker's own engine: a fresh connection per use

    reading = inbox_health.reading_now(imap_svc.is_configured())
    counts = await mandate.run_all(_SessionLocal, datetime.now(timezone.utc), reply_collection_ok=reading)
    return {"status": "ok", "kill_switch": feature_flags.kill_switch(), **counts}


@celery_app.task(name="tasks.mandate_tasks.run_mandates")
def run_mandates() -> dict:
    return run_async(_run)
