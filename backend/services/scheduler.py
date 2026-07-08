"""Campaign step scheduling — dispatches Celery tasks with an ETA instead of
the old in-process asyncio poll loop (see tasks/send_tasks.py for the actual
send logic, which now runs in a Celery worker process, not this one).

Same cumulative-delay semantics as before: step 0 fires at `now`, step 1 at
`now + step0.delay_hours`, step 2 at `now + step0.delay_hours + step1.delay_hours`,
etc., once per assigned lead.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from celery.result import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app import celery_app
from repositories import campaign_repo, outreach_repo
from tasks.send_tasks import send_email_task, send_whatsapp_task

_TASK_BY_CHANNEL = {"email": send_email_task, "whatsapp": send_whatsapp_task}


async def enqueue_campaign(session: AsyncSession, campaign_id: str, org_id: str) -> dict:
    """Schedule every step × every assigned lead with cumulative delays."""
    account_id = uuid.UUID(org_id)
    c = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not c:
        return {"scheduled": 0, "error": "campaign not found"}
    leads = [str(cl.lead_id) for cl in c.leads]
    steps = sorted(c.steps, key=lambda s: s.step_index)
    if not leads or not steps:
        return {"scheduled": 0, "error": "no leads or steps"}

    now = datetime.now(timezone.utc)
    cumulative = 0
    scheduled = 0
    for step in steps:
        cumulative += int(step.delay_hours or 0)
        run_at = now + timedelta(hours=cumulative)
        task = _TASK_BY_CHANNEL[step.channel]
        for lead_id in leads:
            async_result = task.apply_async(
                kwargs={
                    "account_id": org_id,
                    "campaign_id": campaign_id,
                    "campaign_step_id": str(step.id),
                    "lead_id": lead_id,
                },
                eta=run_at,
                queue="sends",
            )
            # Bookkeeping only (Celery/Redis is the actual queue) — lets
            # GET .../schedule list what's pending and cancel-schedule revoke it.
            await outreach_repo.record_outreach_event(
                session,
                account_id,
                channel=step.channel,
                event_type="queued",
                campaign_id=campaign_id,
                campaign_step_id=str(step.id),
                lead_id=lead_id,
                meta={"celery_task_id": async_result.id, "eta": run_at.isoformat()},
            )
            scheduled += 1
    return {"scheduled": scheduled, "steps": len(steps), "leads": len(leads)}


async def pending_for_campaign(session: AsyncSession, campaign_id: str, org_id: str) -> tuple[List[dict], dict]:
    """Real-time status straight from Celery's result backend — not our own
    duplicate bookkeeping, since Celery already tracks PENDING/STARTED/etc."""
    queued_events = await outreach_repo.list_queued_events(session, uuid.UUID(org_id), campaign_id)
    jobs: List[dict] = []
    statuses: List[str] = []
    for event in queued_events:
        task_id = event.meta.get("celery_task_id")
        state: str = AsyncResult(task_id, app=celery_app).state if task_id else "UNKNOWN"
        jobs.append(
            {
                "id": str(event.id),
                "campaign_id": campaign_id,
                "lead_id": str(event.lead_id) if event.lead_id else None,
                "channel": event.channel,
                "run_at": event.meta.get("eta"),
                "status": state,
            }
        )
        statuses.append(state)
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return jobs, counts


async def cancel_campaign(session: AsyncSession, campaign_id: str, org_id: str) -> int:
    queued_events = await outreach_repo.list_queued_events(session, uuid.UUID(org_id), campaign_id)
    cancelled = 0
    for event in queued_events:
        task_id = event.meta.get("celery_task_id")
        if not task_id:
            continue
        result = AsyncResult(task_id, app=celery_app)
        if result.state in ("PENDING", "RETRY"):
            celery_app.control.revoke(task_id)
            cancelled += 1
    return cancelled
