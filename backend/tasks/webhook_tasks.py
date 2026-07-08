"""Periodic retry for webhook events that never got marked `processed` — e.g.
a transient DB error mid-request. Surfaces them via the audit log rather than
re-running the full SendGrid/Twilio parsing logic here (that logic lives in
routes/webhooks.py and isn't yet factored out into a reusable, idempotent
function outside the request path) — a stuck webhook is rare enough that a
visible audit trail plus manual/CI investigation is a reasonable first step.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from celery_app import celery_app
from db.models import WebhookEvent
from tasks._bridge import run_async

STALE_AFTER_MINUTES = 5


async def _retry_unprocessed_webhooks_impl(session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_AFTER_MINUTES)
    result = await session.execute(
        select(WebhookEvent).where(WebhookEvent.processed.is_(False), WebhookEvent.received_at < cutoff)
    )
    stale = result.scalars().all()
    for event in stale:
        event.error = (event.error or "") + " [flagged stale by retry_unprocessed_webhooks]"
    return len(stale)


@celery_app.task(name="tasks.webhook_tasks.retry_unprocessed_webhooks")
def retry_unprocessed_webhooks() -> int:
    return run_async(_retry_unprocessed_webhooks_impl)
