"""Batch Celery scoring of leads with completed, persisted website enrichment."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app import celery_app
from db.models import Company, JobRun, Lead, PublicPageCache
from services.qualification_scoring import score_qualification
from tasks._bridge import run_async

BATCH_SIZE = 200


async def _score_enriched_leads_impl(session: AsyncSession) -> int:
    """Recompute stale enriched leads in bounded transactions; identical reruns are no-ops."""
    cursor = None
    scored = 0
    while True:
        stmt = (
            select(Lead, Company.name, PublicPageCache.url, PublicPageCache.data)
            .outerjoin(Company, Company.id == Lead.company_id)
            .join(
                PublicPageCache,
                or_(
                    and_(Lead.website.is_not(None), PublicPageCache.url == Lead.website),
                    and_(Lead.website.is_(None), PublicPageCache.url == Company.website),
                ),
            )
            .where(
                Lead.deleted_at.is_(None),
                PublicPageCache.status == "completed",
                or_(
                    Lead.qualification_scored_at.is_(None),
                    Lead.updated_at > Lead.qualification_scored_at,
                    PublicPageCache.collected_at > Lead.qualification_scored_at,
                ),
            )
            .order_by(Lead.id)
            .limit(BATCH_SIZE)
        )
        if cursor is not None:
            stmt = stmt.where(Lead.id > cursor)
        rows = (await session.execute(stmt)).all()
        if not rows:
            break

        for lead, company_name, website_url, cache_data in rows:
            result = score_qualification(
                website_url=website_url,
                cache_data=cache_data or {},
                company_name=company_name or lead.company,
                vertical=lead.vertical,
                city=lead.city,
                country=lead.country,
                email=lead.email,
                phone=lead.phone,
                title=lead.title,
            )
            lead.website_quality = result.website_quality
            lead.digital_maturity = result.digital_maturity
            lead.fit_score = result.fit_score
            lead.priority = result.priority
            # Use transaction-stable now() for both timestamps so the next run sees no false staleness.
            lead.qualification_scored_at = func.now()
            lead.updated_at = func.now()
            scored += 1

        cursor = rows[-1][0].id
        await session.flush()
        await session.commit()
    return scored


@celery_app.task(
    name="tasks.qualification_tasks.score_enriched_leads",
    autoretry_for=(SQLAlchemyError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def score_enriched_leads() -> int:
    return run_async(_score_enriched_leads_impl)


async def _score_selected_leads_impl(
    session: AsyncSession, job_id: uuid.UUID, account_id: uuid.UUID, lead_ids: list[uuid.UUID]
) -> dict[str, int]:
    """Score one account-scoped selection and commit progress after each small batch."""
    job = await session.get(JobRun, job_id, with_for_update=True)
    if job is None or job.account_id != account_id:
        return {"processed": 0, "failed": 0}
    if job.status in {"succeeded", "partial", "failed"}:
        return {"processed": job.processed_items, "failed": job.failed_items}

    started_clock = time.monotonic()
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.finished_at = None
    job.duration_ms = None
    job.processed_items = 0
    job.failed_items = 0
    job.error = None
    await session.commit()

    processed = 0
    failed = 0
    for start in range(0, len(lead_ids), 25):
        batch = lead_ids[start : start + 25]
        stmt = (
            select(Lead, Company.name, PublicPageCache.url, PublicPageCache.data, PublicPageCache.collected_at)
            .outerjoin(Company, Company.id == Lead.company_id)
            .outerjoin(
                PublicPageCache,
                and_(
                    PublicPageCache.status == "completed",
                    or_(
                        and_(Lead.website.is_not(None), PublicPageCache.url == Lead.website),
                        and_(Lead.website.is_(None), PublicPageCache.url == Company.website),
                    ),
                ),
            )
            .where(Lead.account_id == account_id, Lead.deleted_at.is_(None), Lead.id.in_(batch))
            .order_by(Lead.id)
            .with_for_update(of=Lead)
        )
        rows = (await session.execute(stmt)).all()
        by_id = {
            lead.id: (lead, company_name, website_url, cache_data, collected_at)
            for lead, company_name, website_url, cache_data, collected_at in rows
        }

        for lead_id in batch:
            row = by_id.get(lead_id)
            if row is None:
                failed += 1
                continue
            lead, company_name, website_url, cache_data, collected_at = row
            if website_url is None:
                failed += 1
                continue

            processed += 1
            stale = (
                lead.qualification_scored_at is None
                or lead.updated_at > lead.qualification_scored_at
                or collected_at > lead.qualification_scored_at
            )
            if stale:
                result = score_qualification(
                    website_url=website_url,
                    cache_data=cache_data or {},
                    company_name=company_name or lead.company,
                    vertical=lead.vertical,
                    city=lead.city,
                    country=lead.country,
                    email=lead.email,
                    phone=lead.phone,
                    title=lead.title,
                )
                lead.website_quality = result.website_quality
                lead.digital_maturity = result.digital_maturity
                lead.fit_score = result.fit_score
                lead.priority = result.priority
                lead.qualification_scored_at = func.now()
                lead.updated_at = func.now()

        job.processed_items = processed
        job.failed_items = failed
        job.error = _selection_error(processed, failed)
        await session.flush()
        await session.commit()

    job = await session.get(JobRun, job_id)
    if job is None:
        return {"processed": processed, "failed": failed}
    job.status = "succeeded" if failed == 0 else "partial" if processed else "failed"
    job.finished_at = datetime.now(timezone.utc)
    job.duration_ms = max(0, int((time.monotonic() - started_clock) * 1000))
    job.error = _selection_error(processed, failed)
    await session.commit()
    return {"processed": processed, "failed": failed}


def _selection_error(processed: int, failed: int) -> str | None:
    if not failed:
        return None
    message = "Some selected leads need completed enrichment or are no longer available."
    return message if processed else "Selected leads need completed enrichment or are no longer available."


async def _mark_selected_job_failed(session: AsyncSession, job_id: uuid.UUID) -> None:
    job = await session.get(JobRun, job_id)
    if job is None or job.status in {"succeeded", "partial", "failed"}:
        return
    now = datetime.now(timezone.utc)
    job.status = "failed"
    job.finished_at = now
    job.duration_ms = max(0, int((now - job.started_at).total_seconds() * 1000)) if job.started_at else None
    job.error = "Scoring job failed. Check the worker status and retry later."


@celery_app.task(
    bind=True,
    name="tasks.qualification_tasks.score_selected_leads",
    max_retries=3,
    retry_backoff=True,
    queue="automation",
)
def score_selected_leads(self, job_id: str, account_id: str, lead_ids: list[str]) -> dict[str, int]:
    """Idempotently score a validated selection; SQL errors retry without exposing details."""
    try:
        return run_async(
            lambda session: _score_selected_leads_impl(
                session,
                uuid.UUID(job_id),
                uuid.UUID(account_id),
                [uuid.UUID(lead_id) for lead_id in lead_ids],
            )
        )
    except SQLAlchemyError:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=RuntimeError("Temporary database error"))
        run_async(lambda session: _mark_selected_job_failed(session, uuid.UUID(job_id)))
        raise RuntimeError("Scoring job failed after database retries.") from None
    except Exception:
        run_async(lambda session: _mark_selected_job_failed(session, uuid.UUID(job_id)))
        raise RuntimeError("Scoring job failed.") from None
