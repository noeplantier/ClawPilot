"""Periodic discovery for active mandates, then automatic drafts for the Hot Leads it produced.

Celery beat calls this task; the worker reuses the same async session bridge as every other task. No network
provider is constructed unless FEATURE_EXTERNAL_SOURCES is enabled, and no mandate is run unless it is active,
unexpired and due by its own cadence. Draft generation is bounded by the mandate's own AI budget and never blocks
the discovery result: it runs in the same worker loop after the Hot Leads are committed, through the existing
`draft_runner` (idempotent jobs, offer guardrail, 0-credit template, short AI personalisation).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select

from celery_app import celery_app
from db.models.prospect import DraftJob
from db.models.prospecting import Mandate, ProspectingBatch, ProspectingBatchItem
from services import ai_svc, draft_runner, feature_flags, mandate_send, smtp_svc
from services.discovery_engine import default_adapters, is_due, run_mandate_discovery
from tasks._bridge import _SessionLocal as celery_sessions
from tasks._bridge import run_async

logger = logging.getLogger("outreachos.mandates")
MAX_MANDATES_PER_SWEEP = 20
PRECISION_TOP_N = 3  # only the best Hot Leads of a run may use the optional precision model


async def _last_run(session, mandate_id):
    return await session.scalar(
        select(ProspectingBatch.created_at)
        .where(ProspectingBatch.config["mandate_id"].astext == str(mandate_id))
        .order_by(desc(ProspectingBatch.created_at))
        .limit(1)
    )


async def _hot_items(session, mandate_id: UUID, *, batch_id: Optional[UUID] = None) -> list[tuple[UUID, dict]]:
    """(lead_id, staged data) of Hot Leads, real rows written by the discovery engine. No batch_id = whole mandate."""
    statement = select(ProspectingBatchItem.lead_id, ProspectingBatchItem.data).where(
        ProspectingBatchItem.stage == "hot"
    )
    if batch_id is not None:
        statement = statement.where(ProspectingBatchItem.batch_id == batch_id)
    else:
        statement = statement.join(ProspectingBatch, ProspectingBatchItem.batch_id == ProspectingBatch.id).where(
            ProspectingBatch.config["mandate_id"].astext == str(mandate_id)
        )
    rows = (await session.execute(statement)).all()
    return [(row.lead_id, row.data or {}) for row in rows if row.lead_id is not None]


async def _ready_leads(session, account_id: UUID, lead_ids: list[UUID]) -> set[UUID]:
    """Mandate spend so far: leads that already have a ready automatic draft (one credit each)."""
    if not lead_ids:
        return set()
    return set(
        (
            await session.execute(
                select(DraftJob.lead_id).where(
                    DraftJob.account_id == account_id,
                    DraftJob.lead_id.in_(lead_ids),
                    DraftJob.status == "ready",
                )
            )
        )
        .scalars()
        .all()
    )


def _best(items: list[tuple[UUID, dict]], limit: int) -> list[UUID]:
    """The best leads are those with the most *detected* signals the discovery engine actually recorded.
    A missing or dismissed signal adds nothing: no score is invented."""

    def score(item: tuple[UUID, dict]) -> int:
        return sum(
            1
            for signal in (item[1].get("signals") or [])
            if isinstance(signal, dict) and signal.get("state") == "detected"
        )

    return [lead_id for lead_id, _ in sorted(items, key=score, reverse=True)[:limit]]


async def _draft_hot_leads(session, mandate: Mandate, batch_id: UUID) -> dict:
    """Trigger one bounded draft sweep for the Hot Leads of this run, respecting the mandate's AI budget."""
    run_hot = await _hot_items(session, mandate.id, batch_id=batch_id)
    if not run_hot:
        return {"started": False, "reason": "no_hot_leads"}
    budget = int(mandate.ai_budget or 0)
    if budget <= 0:
        return {"started": False, "reason": "no_ai_budget"}
    all_hot = await _hot_items(session, mandate.id)
    spent = len(await _ready_leads(session, mandate.account_id, [lead for lead, _ in all_hot]))
    remaining = max(0, budget - spent)
    if remaining <= 0:
        return {"started": False, "reason": "ai_budget_reached"}

    only = [lead for lead, _ in run_hot][:remaining]
    precision = set(_best(run_hot, PRECISION_TOP_N)) & set(only)
    out = await draft_runner.prepare(
        mandate.account_id,
        session_factory=celery_sessions,
        only=only,
        budget=remaining,
        precision_ids=precision,
    )
    return {
        "started": True,
        "budget_remaining": remaining,
        "precision_leads": len(precision),
        "precision_configured": bool(ai_svc.precision_model()),
        **out,
    }


async def _sweep(session) -> dict:
    now = datetime.now(timezone.utc)
    mandates = (
        (
            await session.execute(
                select(Mandate)
                .where(Mandate.status == "active", Mandate.expires_at > now)
                .order_by(Mandate.created_at)
                .limit(MAX_MANDATES_PER_SWEEP)
            )
        )
        .scalars()
        .all()
    )
    adapters = default_adapters()
    ran = []
    for mandate in mandates:
        last = await _last_run(session, mandate.id)
        if not is_due(last, mandate.cadence_minutes, now):
            continue
        result = await run_mandate_discovery(session, mandate, adapters=adapters, now=now)
        # The draft sweep opens its own worker sessions: commit the staged Hot Leads first so it can see them.
        await session.commit()
        drafts = await _draft_hot_leads(session, mandate, UUID(result["batch_id"]))
        ran.append({"mandate_id": str(mandate.id), **result, "drafts": drafts})
    return {"mandates_checked": len(mandates), "mandates_run": len(ran), "runs": ran}


@celery_app.task(name="tasks.outreach_mandate_tasks.run_due_mandate_discovery", bind=True, max_retries=0)
def run_due_mandate_discovery(self):
    """Run due active mandates, then prepare drafts for their Hot Leads. A disabled source flag is a skip."""
    if not feature_flags.is_enabled("external_sources"):
        return {"skipped": "FEATURE_EXTERNAL_SOURCES is off"}
    return run_async(_sweep)


@celery_app.task(name="tasks.outreach_mandate_tasks.process_mandate_sends", bind=True, max_retries=0)
def process_mandate_sends(self):
    """Plan and send what is due for active mandates through the common dispatch and its guardrails."""

    async def _send(session):
        return await mandate_send.send_due(
            session, now=datetime.now(timezone.utc), live_adapter=smtp_svc.adapter_from_env()
        )

    return run_async(_send)


@celery_app.task(name="tasks.outreach_mandate_tasks.mandate_daily_report", bind=True, max_retries=0)
def mandate_daily_report(self):
    """Compact daily journal: only counts the ledger really holds."""

    async def _report(session):
        return await mandate_send.daily_report(session, now=datetime.now(timezone.utc))

    return run_async(_report)
