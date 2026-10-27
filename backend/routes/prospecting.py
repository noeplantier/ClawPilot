"""Authenticated public map discovery and manual CRM conversion endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AuditLog,
    Company,
    Contact,
    DiscoveredPlace,
    DiscoveryJob,
    EnrichmentJob,
    Lead,
    LeadSource,
    Note,
)
from db.session import get_db_session
from deps import get_current_user
from services import feature_flags
from tasks.prospecting_tasks import _key, discover_task, enrich_task

router = APIRouter(prefix="/prospecting", tags=["prospecting"])


def _need_external_sources() -> None:
    """Overpass and the businesses' own sites are network sources: off unless FEATURE_EXTERNAL_SOURCES is set."""
    if not feature_flags.is_enabled("external_sources"):
        raise HTTPException(status_code=409, detail="Map discovery needs FEATURE_EXTERNAL_SOURCES (off by default)")


Category = Literal["restaurant", "cafe", "hotel", "shop", "office", "beauty", "dentist", "company"]


class DiscoveryIn(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    category: Category

    @model_validator(mode="after")
    def validate_bbox(self):
        south, west, north, east = self.bbox
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ValueError("Invalid bbox")
        if north - south > 0.12 or east - west > 0.12:
            raise ValueError("Area exceeds the public Overpass search limit")
        return self


class ConvertIn(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=4000)


@router.post("/search", status_code=202)
async def search(
    payload: DiscoveryIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    _need_external_sources()
    account_id = uuid.UUID(user["org_id"])
    key = _key(payload.bbox, payload.category)
    now = datetime.now(timezone.utc)
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"{account_id}:{key}", 0))))
    job = await session.scalar(
        select(DiscoveryJob).where(
            DiscoveryJob.account_id == account_id,
            DiscoveryJob.cache_key == key,
        )
    )
    if job and job.expires_at > now:
        if job.status in ("queued", "running"):
            return {"job_id": str(job.id), "status": job.status, "cached": True}
        if job.status == "completed":
            return {"job_id": str(job.id), "status": job.status, "cached": True}
    if job:
        job.status = "queued"
        job.error_code = None
        job.completed_at = None
        job.result_count = 0
        job.expires_at = now + timedelta(hours=12)
        job.bbox = [round(value, 4) for value in payload.bbox]
    else:
        job = DiscoveryJob(
            account_id=account_id,
            cache_key=key,
            bbox=[round(value, 4) for value in payload.bbox],
            category=payload.category,
            status="queued",
            expires_at=now + timedelta(hours=12),
        )
        session.add(job)
    await session.flush()
    await session.commit()
    try:
        discover_task.apply_async(args=[str(job.id)], queue="automation")
    except Exception:
        job.status = "failed"
        job.error_code = "queue_unavailable"
        await session.commit()
        raise HTTPException(status_code=503, detail="Discovery queue unavailable")
    return {"job_id": str(job.id), "status": "queued", "cached": False}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(500, ge=1, le=500),
):
    account_id = uuid.UUID(user["org_id"])
    job = await session.scalar(
        select(DiscoveryJob).where(
            DiscoveryJob.id == uuid.UUID(job_id),
            DiscoveryJob.account_id == account_id,
        )
    )
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    result = await session.execute(
        select(DiscoveredPlace)
        .where(
            DiscoveredPlace.account_id == account_id,
            DiscoveredPlace.job_id == job.id,
        )
        .order_by(DiscoveredPlace.name)
        .limit(limit)
    )
    places = result.scalars().all()
    return {
        "job_id": str(job.id),
        "status": job.status,
        "result_count": job.result_count,
        "error_code": job.error_code,
        "places": [
            {
                "id": str(place.id),
                "name": place.name,
                "latitude": place.latitude,
                "longitude": place.longitude,
                "category": place.category,
                "address": place.address,
                "website": place.website,
                "phone": place.phone,
                "lead_id": str(place.lead_id) if place.lead_id else None,
            }
            for place in places
        ],
    }


@router.post("/places/{place_id}/convert")
async def convert(
    place_id: str,
    payload: ConvertIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    place = await session.scalar(
        select(DiscoveredPlace)
        .where(
            DiscoveredPlace.id == uuid.UUID(place_id),
            DiscoveredPlace.account_id == account_id,
        )
        .with_for_update()
    )
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    if place.lead_id:
        return {"lead_id": str(place.lead_id), "created": False}
    source = await session.scalar(
        select(LeadSource).where(
            LeadSource.account_id == account_id,
            LeadSource.name == "OpenStreetMap / Overpass",
        )
    )
    if not source:
        source = LeadSource(
            account_id=account_id,
            name="OpenStreetMap / Overpass",
            kind="api",
            config={"attribution": "© OpenStreetMap contributors"},
        )
        session.add(source)
        await session.flush()
    company = await session.scalar(
        select(Company).where(
            Company.account_id == account_id,
            Company.source_key == place.source_key,
        )
    )
    if not company:
        company = Company(
            account_id=account_id,
            source_key=place.source_key,
            name=place.name,
            website=place.website,
            phone=place.phone,
            address=place.address,
        )
        session.add(company)
        await session.flush()
    lead = Lead(
        account_id=account_id,
        full_name=place.name,
        company=place.name,
        company_id=company.id,
        phone=place.phone,
        stage="new",
        tags=list(payload.tags),
        source_id=source.id,
        notes=payload.notes,
    )
    session.add(lead)
    await session.flush()
    contact_name = place.tags.get("contact:person") or place.tags.get("contact:name")
    if isinstance(contact_name, str) and contact_name.strip():
        session.add(
            Contact(
                account_id=account_id,
                lead_id=lead.id,
                full_name=contact_name.strip()[:300],
                phone=place.phone,
                is_primary=True,
            )
        )
    place.lead_id = lead.id
    user_id = uuid.UUID(user["id"])
    session.add(
        Note(
            account_id=account_id,
            lead_id=lead.id,
            author_user_id=user_id,
            body="Découvert via carte — OpenStreetMap / Overpass",
        )
    )
    session.add(
        AuditLog(
            account_id=account_id,
            actor_user_id=user_id,
            actor_type="user",
            action="lead.discovered_via_map",
            resource_type="lead",
            resource_id=lead.id,
            diff={"source_key": place.source_key, "place_id": str(place.id)},
        )
    )
    await session.flush()
    return {"lead_id": str(lead.id), "created": True}


@router.post("/leads/{lead_id}/enrich", status_code=202)
async def enqueue_enrichment(
    lead_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    _need_external_sources()
    account_id = uuid.UUID(user["org_id"])
    lead = await session.scalar(
        select(Lead).where(
            Lead.id == uuid.UUID(lead_id),
            Lead.account_id == account_id,
            Lead.deleted_at.is_(None),
        )
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    active = EnrichmentJob.status.in_(["queued", "running"])
    existing = await session.scalar(
        select(EnrichmentJob).where(
            EnrichmentJob.account_id == account_id,
            EnrichmentJob.lead_id == lead.id,
            active,
        )
    )
    if existing:
        return {"job_id": str(existing.id), "status": existing.status, "cached": True}
    statement = (
        insert(EnrichmentJob)
        .values(account_id=account_id, lead_id=lead.id, status="queued")
        .on_conflict_do_nothing(
            index_elements=["account_id", "lead_id"],
            index_where=text("status IN ('queued','running')"),
        )
        .returning(EnrichmentJob.id)
    )
    created_id = (await session.execute(statement)).scalar_one_or_none()
    if created_id is None:
        existing = await session.scalar(
            select(EnrichmentJob).where(
                EnrichmentJob.account_id == account_id,
                EnrichmentJob.lead_id == lead.id,
                active,
            )
        )
        return {"job_id": str(existing.id), "status": existing.status, "cached": True}
    job = await session.get(EnrichmentJob, created_id)
    await session.commit()
    try:
        enrich_task.apply_async(args=[str(created_id)], queue="automation")
    except Exception:
        job.status = "failed"
        await session.commit()
        raise HTTPException(status_code=503, detail="Enrichment queue unavailable")
    return {"job_id": str(created_id), "status": "queued", "cached": False}
