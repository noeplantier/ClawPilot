"""Periodic automation — Celery beat schedule lives in celery_app.py.

Each task loops over accounts/leads and reuses the same repositories the HTTP
routes use; there is no separate "automation data layer".
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery.result import AsyncResult
from sqlalchemy import select

from celery_app import celery_app
from db.models import Lead, OutreachEvent
from repositories import account_repo, audit_repo, lead_repo
from tasks._bridge import run_async
from tasks.send_tasks import send_email_task, send_whatsapp_task

logger = logging.getLogger("outreachos.automation")

DORMANT_AFTER_DAYS = 30
UNQUALIFIED_SCORE_THRESHOLD = 15
_TASK_BY_CHANNEL = {"email": send_email_task, "whatsapp": send_whatsapp_task}


async def _advance_due_campaign_steps_impl(session) -> int:
    """Safety net for apply_async(eta=...) sends lost to a worker restart past
    the broker's visibility window — not the primary delivery mechanism."""
    now = datetime.now(timezone.utc)
    result = await session.execute(select(OutreachEvent).where(OutreachEvent.event_type == "queued"))
    requeued = 0
    for event in result.scalars().all():
        eta_raw = event.meta.get("eta")
        task_id = event.meta.get("celery_task_id")
        if not eta_raw or not task_id:
            continue
        eta = datetime.fromisoformat(eta_raw)
        if eta.tzinfo is None:
            eta = eta.replace(tzinfo=timezone.utc)
        if now - eta < timedelta(minutes=2):
            continue  # not due long enough yet to consider it "lost"

        state = AsyncResult(task_id, app=celery_app).state
        if state not in ("PENDING",):
            continue  # already ran (or is retrying, which is fine)

        # Confirm nothing completed for this (step, lead) after it was queued.
        completed = await session.execute(
            select(OutreachEvent.id).where(
                OutreachEvent.campaign_step_id == event.campaign_step_id,
                OutreachEvent.lead_id == event.lead_id,
                OutreachEvent.event_type.in_(["sent", "failed"]),
                OutreachEvent.occurred_at > event.occurred_at,
            )
        )
        if completed.scalar_one_or_none():
            continue

        task = _TASK_BY_CHANNEL.get(event.channel)
        if not task:
            continue
        task.apply_async(
            kwargs={
                "account_id": str(event.account_id),
                "campaign_id": str(event.campaign_id),
                "campaign_step_id": str(event.campaign_step_id),
                "lead_id": str(event.lead_id),
            },
            queue="sends",
        )
        requeued += 1
        logger.warning("Re-dispatched lost send for lead %s (original task %s)", event.lead_id, task_id)
    return requeued


async def _rescore_all_active_leads_impl(session) -> int:
    total = 0
    for account_id in await account_repo.list_all_account_ids(session):
        total += await lead_repo.enrich_leads(session, account_id)
    return total


async def _stop_unqualified_sequences_impl(session) -> int:
    """Cancels pending queued sends for leads that scored too low to be worth
    continuing to contact — mirrors campaigns.py's cancel-schedule, just
    triggered by score instead of by campaign."""
    cancelled = 0
    for account_id in await account_repo.list_all_account_ids(session):
        low_scorers = await session.execute(
            select(Lead.id).where(
                Lead.account_id == account_id,
                Lead.deleted_at.is_(None),
                Lead.stage == "new",
                Lead.score < UNQUALIFIED_SCORE_THRESHOLD,
            )
        )
        lead_ids = {row[0] for row in low_scorers.all()}
        if not lead_ids:
            continue

        queued = await session.execute(
            select(OutreachEvent).where(
                OutreachEvent.account_id == account_id,
                OutreachEvent.event_type == "queued",
                OutreachEvent.lead_id.in_(lead_ids),
            )
        )
        for event in queued.scalars().all():
            task_id = event.meta.get("celery_task_id")
            if not task_id:
                continue
            if AsyncResult(task_id, app=celery_app).state in ("PENDING", "RETRY"):
                celery_app.control.revoke(task_id)
                cancelled += 1
        if cancelled:
            await audit_repo.log(
                session,
                account_id,
                action="automation.stop_unqualified",
                resource_type="lead",
                actor_type="celery_task",
                diff={"cancelled_sends": cancelled, "threshold": UNQUALIFIED_SCORE_THRESHOLD},
            )
    return cancelled


async def _reactivate_dormant_leads_impl(session) -> int:
    """Surfaces dormant leads (tag + audit log) for a human to decide what to
    do next — auto-selecting and launching a whole new campaign without any
    configured rule for *which* campaign is out of scope here (see the Phase 4
    automation-rules engine backlog item)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DORMANT_AFTER_DAYS)
    tagged = 0
    for account_id in await account_repo.list_all_account_ids(session):
        candidates = await session.execute(
            select(Lead).where(
                Lead.account_id == account_id,
                Lead.deleted_at.is_(None),
                Lead.stage.in_(["contacted", "engaged"]),
            )
        )
        for lead in candidates.scalars().all():
            last_event = await session.execute(
                select(OutreachEvent.occurred_at)
                .where(OutreachEvent.lead_id == lead.id)
                .order_by(OutreachEvent.occurred_at.desc())
                .limit(1)
            )
            last_at = last_event.scalar_one_or_none() or lead.created_at
            if last_at > cutoff or "dormant" in lead.tags:
                continue
            lead.tags = sorted(set(lead.tags) | {"dormant"})
            tagged += 1
            await audit_repo.log(
                session,
                account_id,
                action="automation.reactivate_dormant",
                resource_type="lead",
                resource_id=lead.id,
                actor_type="celery_task",
                diff={
                    "last_activity": last_at.isoformat(),
                    "days_inactive": (datetime.now(timezone.utc) - last_at).days,
                },
            )
    return tagged


@celery_app.task(name="tasks.automation_tasks.advance_due_campaign_steps")
def advance_due_campaign_steps() -> int:
    return run_async(_advance_due_campaign_steps_impl)


@celery_app.task(name="tasks.automation_tasks.rescore_all_active_leads")
def rescore_all_active_leads() -> int:
    return run_async(_rescore_all_active_leads_impl)


@celery_app.task(name="tasks.automation_tasks.stop_unqualified_sequences")
def stop_unqualified_sequences() -> int:
    return run_async(_stop_unqualified_sequences_impl)


@celery_app.task(name="tasks.automation_tasks.reactivate_dormant_leads")
def reactivate_dormant_leads() -> int:
    return run_async(_reactivate_dormant_leads_impl)
