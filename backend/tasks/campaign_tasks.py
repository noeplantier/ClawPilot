"""Sends what an individual campaign has planned, one message at a time, when its time has come.

Runs every minute on the `sends` queue (Celery Beat). The work is in services/campaign_launch.process_due: every gate
is checked again for each message at the moment it would leave, and the message goes through the same dispatch as every
other path (kill switch, pause, suppression, consent, compliance, limits, sandbox, at most once). A refusal that time
can fix reschedules the message; one that cannot stops it; nothing is retried after an unclear outcome.
"""

from __future__ import annotations

from datetime import datetime, timezone

from celery_app import celery_app
from services import campaign_launch, smtp_svc
from tasks._bridge import run_async


async def _process_due_impl(session) -> dict:
    return await campaign_launch.process_due(
        session, now=datetime.now(timezone.utc), live_adapter=smtp_svc.adapter_from_env()
    )


@celery_app.task(name="tasks.campaign_tasks.process_due_dispatches")
def process_due_dispatches() -> dict:
    return run_async(_process_due_impl)
