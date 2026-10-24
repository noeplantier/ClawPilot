"""Leads / CRM routes — Postgres-backed (leads + lead_sources tables)."""

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, cast

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Company, JobRun
from db.models import Lead as LeadRow
from db.models import PublicPageCache
from db.session import get_db_session
from deps import get_current_user
from models import (
    ConsentStatus,
    ConsentUpdateIn,
    HeatOut,
    Lead,
    LeadCreate,
    LeadUpdate,
    ScoreLeadsIn,
    ScoreLeadsQueued,
)
from repositories import activity_repo, consent_repo, lead_repo, tags_repo
from repositories.lead_repo import LeadExtra
from services.outreach_os import heat as heat_rules
from tasks.qualification_tasks import score_selected_leads as score_selected_leads_task

router = APIRouter(prefix="/leads", tags=["leads"])
logger = logging.getLogger(__name__)


def _score_of(lead, extra: LeadExtra) -> Optional[int]:
    """The score a lead is ranked on: a discovery prospect's latest score, else the CRM score (0 means not scored)."""
    if extra.prospect_score is not None:
        return extra.prospect_score
    return lead.score if lead.score > 0 else None


def _heat(lead, extra: LeadExtra) -> HeatOut:
    """Heat of a lead: its real information and, when it has one, its score."""
    h = heat_rules.heat_of(
        {
            "email": lead.email,
            "phone": lead.phone,
            "website": lead.website,
            "city": lead.city,
            "company": lead.company,
            "vertical": lead.vertical,
            "country": lead.country,
            "title": lead.title,
        },
        _score_of(lead, extra),
    )
    return HeatOut(
        value=h.value,
        tier=h.tier,
        info_pct=h.info_pct,
        known=list(h.known),
        missing=list(h.missing),
        scored=h.scored,
        top=h.top,
        has_contact=h.has_contact,
        score=h.score,
    )


def _to_schema(lead, extra: LeadExtra, *, enrichment_completed: bool = False) -> Lead:
    return Lead(
        id=str(lead.id),
        org_id=str(lead.account_id),
        full_name=lead.full_name,
        email=lead.email,
        phone=lead.phone,
        company=lead.company,
        title=lead.title,
        country=lead.country,
        language=lead.language,
        stage=lead.stage,
        tags=list(lead.tags),
        source=extra.source,
        notes=lead.notes,
        score=extra.prospect_score if extra.prospect_score is not None else lead.score,
        email_consent=cast(ConsentStatus, extra.email_consent),
        whatsapp_consent=cast(ConsentStatus, extra.whatsapp_consent),
        created_at=lead.created_at,
        city=lead.city,
        website=lead.website,
        vertical=lead.vertical,
        heat=_heat(lead, extra),
        website_quality=lead.website_quality,
        digital_maturity=lead.digital_maturity,
        fit_score=lead.fit_score,
        priority=lead.priority,
        qualification_scored_at=lead.qualification_scored_at,
        enrichment_status="completed" if enrichment_completed else "required",
        review_status=lead.review_status,
    )


async def _enriched_lead_ids(session: AsyncSession, lead_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not lead_ids:
        return set()
    completed_cache = (
        select(PublicPageCache.id)
        .where(
            PublicPageCache.status == "completed",
            or_(
                and_(LeadRow.website.is_not(None), PublicPageCache.url == LeadRow.website),
                and_(LeadRow.website.is_(None), PublicPageCache.url == Company.website),
            ),
        )
        .correlate(LeadRow, Company)
        .exists()
    )
    return set(
        (
            await session.execute(
                select(LeadRow.id)
                .outerjoin(Company, Company.id == LeadRow.company_id)
                .where(LeadRow.id.in_(lead_ids), completed_cache)
            )
        ).scalars()
    )


class BulkLeadsIn(BaseModel):
    leads: List[LeadCreate]


class BulkLeadsOut(BaseModel):
    created: int
    skipped: int
    errors: List[str]
    lead_ids: List[str]


class BulkStageIn(BaseModel):
    lead_ids: List[str]
    stage: str


class BulkDeleteIn(BaseModel):
    lead_ids: List[str]


class BulkTagIn(BaseModel):
    lead_ids: List[str]
    tags: List[str]
    mode: str = "add"  # add | replace


@router.get("", response_model=List[Lead])
async def list_leads(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    stage: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = Query("heat", pattern="^(heat|recent)$"),
    limit: int = Query(500, le=1000),
):
    """Hottest first by default: real information and score (see services/outreach_os/heat.py)."""
    rows = await lead_repo.list_leads(
        session, uuid.UUID(user["org_id"]), stage=stage, search=search, sort=sort, limit=limit
    )
    if not rows:
        return []
    enriched_ids = await _enriched_lead_ids(session, [lead.id for lead, _ in rows])
    return [_to_schema(lead, extra, enrichment_completed=lead.id in enriched_ids) for lead, extra in rows]


@router.post("", response_model=Lead)
async def create_lead(
    payload: LeadCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        lead, extra = await lead_repo.create_lead(session, uuid.UUID(user["org_id"]), payload.model_dump())
    except lead_repo.DuplicateEmail:
        raise HTTPException(status_code=409, detail="A lead with this email already exists")
    await activity_repo.record(session, user["org_id"], "lead.created", f"New lead added — {lead.full_name}")
    enriched_ids = await _enriched_lead_ids(session, [lead.id])
    return _to_schema(lead, extra, enrichment_completed=lead.id in enriched_ids)


@router.post("/score", response_model=ScoreLeadsQueued, status_code=202)
async def score_selected_leads(
    payload: ScoreLeadsIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    lead_ids = payload.lead_ids
    owned_ids = set(
        (
            await session.execute(
                select(LeadRow.id).where(
                    LeadRow.account_id == account_id,
                    LeadRow.deleted_at.is_(None),
                    LeadRow.id.in_(lead_ids),
                )
            )
        ).scalars()
    )
    if owned_ids != set(lead_ids):
        # Do not reveal whether a foreign or deleted lead exists.
        raise HTTPException(status_code=404, detail="One or more leads were not found")

    job = JobRun(
        account_id=account_id,
        job_type="manual_lead_scoring",
        status="queued",
        total_items=len(lead_ids),
        created_by=uuid.UUID(user["id"]),
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)
    job_id = job.id
    await session.commit()  # Persist before enqueue so the worker can always load the job.

    try:
        score_selected_leads_task.apply_async(
            args=(str(job_id), str(account_id), [str(lead_id) for lead_id in lead_ids]),
            task_id=str(job_id),
            queue="automation",
        )
    except Exception as exc:  # noqa: BLE001 - provider/transport detail must never reach the client or job row.
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.duration_ms = 0
        job.error = "The scoring job could not be queued."
        await session.commit()
        logger.warning(
            "Scoring job enqueue failed",
            extra={
                "job_id": str(job_id),
                "account_id": str(account_id),
                "requested_by": user["id"],
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(status_code=503, detail="Scoring service is temporarily unavailable") from None

    logger.info(
        "Scoring job queued",
        extra={
            "job_id": str(job_id),
            "account_id": str(account_id),
            "lead_count": len(lead_ids),
            "requested_by": user["id"],
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "status": job.status,
        },
    )
    return ScoreLeadsQueued(job_id=str(job_id), status="queued", lead_count=len(lead_ids))


@router.post("/bulk", response_model=BulkLeadsOut)
async def bulk_create_leads(
    payload: BulkLeadsIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Bulk import — dedupes by email within org."""
    result = await lead_repo.bulk_create_leads(
        session, uuid.UUID(user["org_id"]), [row.model_dump() for row in payload.leads]
    )
    await activity_repo.record(
        session,
        user["org_id"],
        "lead.bulk",
        f"Bulk import · +{result.created} leads ({result.skipped} duplicates skipped)",
    )
    return BulkLeadsOut(created=result.created, skipped=result.skipped, errors=result.errors, lead_ids=result.lead_ids)


@router.post("/bulk-stage")
async def bulk_update_stage(
    payload: BulkStageIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    updated = await lead_repo.bulk_update_stage(session, uuid.UUID(user["org_id"]), payload.lead_ids, payload.stage)
    await activity_repo.record(
        session, user["org_id"], "lead.bulk_stage", f"Bulk stage update → {payload.stage} · {updated} leads"
    )
    return {"updated": updated}


@router.post("/bulk-delete")
async def bulk_delete_leads(
    payload: BulkDeleteIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    deleted = await lead_repo.bulk_delete_leads(session, uuid.UUID(user["org_id"]), payload.lead_ids)
    await activity_repo.record(session, user["org_id"], "lead.bulk_delete", f"Bulk delete · {deleted} leads removed")
    return {"deleted": deleted}


@router.post("/bulk-tag")
async def bulk_tag_leads(
    payload: BulkTagIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    updated = await lead_repo.bulk_tag_leads(
        session, uuid.UUID(user["org_id"]), payload.lead_ids, payload.tags, payload.mode
    )
    await activity_repo.record(
        session, user["org_id"], "lead.bulk_tag", f"Bulk {payload.mode} tags {payload.tags} · {updated} leads"
    )
    return {"updated": updated}


@router.post("/upload-csv", response_model=BulkLeadsOut)
async def upload_csv(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload a CSV file. Expected columns (any subset, case-insensitive):
    full_name OR name, email, phone, company, title, country, language, tags (comma-split),
    source, notes, email_opt_in, whatsapp_opt_in (any of 1/true/yes/y counts as opted in)
    """
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file has no header row")

    lowered = {h.strip().lower(): h for h in reader.fieldnames}
    TRUTHY = {"1", "true", "yes", "y"}

    def pick(row: dict, *candidates) -> Optional[str]:
        for c in candidates:
            key = lowered.get(c)
            if key and row.get(key):
                return str(row[key]).strip()
        return None

    def pick_bool(row: dict, *candidates) -> bool:
        value = pick(row, *candidates)
        return value is not None and value.strip().lower() in TRUTHY

    items: List[LeadCreate] = []
    errors: List[str] = []
    for i, row in enumerate(reader, start=2):
        try:
            name = pick(row, "full_name", "name")
            if not name:
                continue
            tag_raw = pick(row, "tags", "tag")
            tags = [t.strip() for t in tag_raw.split(",")] if tag_raw else []
            items.append(
                LeadCreate(
                    full_name=name,
                    email=pick(row, "email"),
                    phone=pick(row, "phone", "mobile"),
                    company=pick(row, "company", "organization"),
                    title=pick(row, "title", "role"),
                    country=pick(row, "country"),
                    language=pick(row, "language", "lang") or "en",
                    tags=tags,
                    source=pick(row, "source") or "csv_upload",
                    notes=pick(row, "notes"),
                    email_opt_in=pick_bool(row, "email_opt_in", "email_consent"),
                    whatsapp_opt_in=pick_bool(row, "whatsapp_opt_in", "whatsapp_consent"),
                    consent_source="csv_upload",
                )
            )
        except Exception as e:
            errors.append(f"row {i}: {str(e)[:100]}")

    # Reuse bulk logic
    result = await bulk_create_leads(BulkLeadsIn(leads=items), user=user, session=session)
    # Merge CSV-parse errors
    result.errors = errors + result.errors
    return result


@router.get("/{lead_id}", response_model=Lead)
async def get_lead(
    lead_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    lead = await lead_repo.get_lead(session, uuid.UUID(user["org_id"]), lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    extra = await lead_repo.load_extra(session, lead)
    enriched_ids = await _enriched_lead_ids(session, [lead.id])
    return _to_schema(lead, extra, enrichment_completed=lead.id in enriched_ids)


@router.patch("/{lead_id}", response_model=Lead)
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        res = await lead_repo.update_lead(session, uuid.UUID(user["org_id"]), lead_id, upd)
    except lead_repo.DuplicateEmail:
        raise HTTPException(status_code=409, detail="A lead with this email already exists")
    if not res:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead, extra = res
    if "stage" in upd:
        await activity_repo.record(session, user["org_id"], "lead.stage", f"{lead.full_name} → {upd['stage']}")
    enriched_ids = await _enriched_lead_ids(session, [lead.id])
    return _to_schema(lead, extra, enrichment_completed=lead.id in enriched_ids)


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ok = await lead_repo.delete_lead(session, uuid.UUID(user["org_id"]), lead_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"ok": True}


@router.post("/enrich")
async def enrich_leads(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Recompute the weighted score for every active lead in the account (role,
    country, tags, source intent, engagement history — see services/scoring.py).
    Each recomputation is recorded in `lead_scores` for a full audit trail."""
    count = await lead_repo.enrich_leads(session, uuid.UUID(user["org_id"]))
    await activity_repo.record(session, user["org_id"], "lead.rescored", f"Rescored {count} leads")
    return {"enriched": count}


@router.post("/{lead_id}/consent")
async def update_consent(
    lead_id: str,
    payload: ConsentUpdateIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Record an explicit opt-in/opt-out for a lead's primary contact — the only
    other ways consent changes are the SendGrid unsubscribe webhook and a
    WhatsApp STOP reply (both automatic). See repositories/consent_repo.py for
    the enforcement policy this feeds (strict opt-in for WhatsApp, opt-out
    respect for email)."""
    account_id = uuid.UUID(user["org_id"])
    lead = await lead_repo.get_lead(session, account_id, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
    if not contact_id:
        raise HTTPException(status_code=400, detail="Lead has no contact to attach consent to")

    await consent_repo.record_consent(
        session,
        account_id,
        contact_id,
        channel=payload.channel,
        status=payload.status,
        source=payload.source,
    )
    await activity_repo.record(
        session,
        user["org_id"],
        "lead.consent",
        f"{lead.full_name} · {payload.channel} → {payload.status} ({payload.source})",
    )
    return {"ok": True, "channel": payload.channel, "status": payload.status}


@router.post("/{lead_id}/tags/{tag_id}", response_model=Lead)
async def attach_tag(
    lead_id: str,
    tag_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    lead = await tags_repo.attach_tag(session, uuid.UUID(user["org_id"]), lead_id, tag_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead or tag not found")
    extra = await lead_repo.load_extra(session, lead)
    enriched_ids = await _enriched_lead_ids(session, [lead.id])
    return _to_schema(lead, extra, enrichment_completed=lead.id in enriched_ids)


@router.delete("/{lead_id}/tags/{tag_id}", response_model=Lead)
async def detach_tag(
    lead_id: str,
    tag_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    lead = await tags_repo.detach_tag(session, uuid.UUID(user["org_id"]), lead_id, tag_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead or tag not found")
    extra = await lead_repo.load_extra(session, lead)
    enriched_ids = await _enriched_lead_ids(session, [lead.id])
    return _to_schema(lead, extra, enrichment_completed=lead.id in enriched_ids)
