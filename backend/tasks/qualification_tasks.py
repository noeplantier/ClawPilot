"""Batch Celery scoring of leads with completed, persisted website enrichment."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app import celery_app
from db.models import Company, Lead, PublicPageCache
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
