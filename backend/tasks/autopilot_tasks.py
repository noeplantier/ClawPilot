"""Scheduled visit of the autopilots that owners turned on (services/autopilot_runner.py). Never sends a message."""

from __future__ import annotations

import logging

from celery_app import celery_app
from services import autopilot_runner
from tasks._bridge import run_async

logger = logging.getLogger("outreachos.autopilot")


async def _run(_session) -> dict:
    from tasks._bridge import _SessionLocal  # the worker's own engine: a fresh connection per use

    return await autopilot_runner.run_all(session_factory=_SessionLocal)


@celery_app.task(name="tasks.autopilot_tasks.run_autopilots")
def run_autopilots() -> dict:
    return run_async(_run)
