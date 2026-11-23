"""Bounded prospecting mandates.

A mandate is the one authorisation an owner/admin gives once. Creating it is a draft and starts nothing: activation is
a separate, explicit decision. This route only records and controls that decision — discovery, drafts and sending are
other stages and are deliberately not wired here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.workspace import AuditLog
from db.models.outbound import OutboundMessage
from db.models.prospect import DraftJob, DRAFT_JOB_STATUSES
from db.models.prospecting import Mandate, ProspectingBatch, ProspectingBatchItem
from db.session import get_db_session
from deps import get_current_user, require_roles
from services import mandate_send

router = APIRouter(prefix="/outreach-mandates", tags=["outreach-mandates"])
decider = require_roles("owner", "admin")


class ZoneIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    bbox: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def bounded(self):
        south, west, north, east = self.bbox
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ValueError("Invalid bounding box")
        if north - south > 0.12 or east - west > 0.12:
            raise ValueError("Area exceeds the public Overpass search limit")
        return self


class WindowIn(BaseModel):
    start_hour: int = Field(ge=0, le=23)  # UTC
    end_hour: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_hour <= self.start_hour:
            raise ValueError("end_hour must be after start_hour")
        return self


class MandateIn(BaseModel):
    zone: ZoneIn
    sector: str = Field(min_length=1, max_length=120)
    offer: str = Field(min_length=1, max_length=4000)
    qualification_criteria: list[str] = Field(default_factory=list, max_length=20)
    daily_volume: int = Field(ge=1, le=200)
    total_volume: int = Field(ge=1, le=100_000)
    ai_budget: float = Field(ge=0, le=10_000)
    time_windows: list[WindowIn] = Field(min_length=1, max_length=7)
    cadence_minutes: int = Field(ge=60, le=10_080)  # hourly at most, weekly at least
    expires_at: datetime
    stop_rules: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def coherent(self):
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if self.expires_at <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        if self.daily_volume > self.total_volume:
            raise ValueError("daily_volume cannot exceed total_volume")
        return self


class MandateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    zone: dict
    sector: str
    offer: str
    qualification_criteria: list
    daily_volume: int
    total_volume: int
    ai_budget: float
    time_windows: list
    cadence_minutes: int
    expires_at: datetime
    stop_rules: list
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class BatchOut(BaseModel):
    id: str
    status: str
    counters: dict
    exclusion_reasons: dict
    error_summary: Optional[str] = None
    checkpoint: dict
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class BatchItemOut(BaseModel):
    id: str
    name: str
    category: str
    stage: str
    exclusion_reason: Optional[str] = None
    data: dict
    created_at: datetime


def _to_out(row: Mandate) -> MandateOut:
    return MandateOut(
        id=str(row.id),
        status=row.status,
        zone=row.zone,
        sector=row.sector,
        offer=row.offer,
        qualification_criteria=row.qualification_criteria,
        daily_volume=row.daily_volume,
        total_volume=row.total_volume,
        ai_budget=float(row.ai_budget),
        time_windows=row.time_windows,
        cadence_minutes=row.cadence_minutes,
        expires_at=row.expires_at,
        stop_rules=row.stop_rules,
        approved_at=row.approved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _owned(session: AsyncSession, user: dict, mandate_id: str) -> Mandate:
    try:
        identifier = uuid.UUID(mandate_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Mandate not found")
    row = await session.scalar(
        select(Mandate).where(
            Mandate.id == identifier,
            Mandate.account_id == uuid.UUID(user["org_id"]),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return row


def _transition(row: Mandate, allowed: tuple[str, ...], target: str) -> None:
    if row.status not in allowed:
        raise HTTPException(status_code=409, detail=f"Mandate is {row.status}: cannot move to {target}")
    row.status = target


@router.post("", response_model=MandateOut, status_code=201)
async def create_mandate(
    payload: MandateIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Record a bounded mandate as a draft. Nothing is discovered, drafted or sent by this call."""
    row = Mandate(
        account_id=uuid.UUID(user["org_id"]),
        created_by_user_id=uuid.UUID(user["id"]),
        status="draft",
        zone=payload.zone.model_dump(),
        sector=payload.sector,
        offer=payload.offer,
        qualification_criteria=payload.qualification_criteria,
        daily_volume=payload.daily_volume,
        total_volume=payload.total_volume,
        ai_budget=payload.ai_budget,
        time_windows=[window.model_dump() for window in payload.time_windows],
        cadence_minutes=payload.cadence_minutes,
        expires_at=payload.expires_at,
        stop_rules=payload.stop_rules,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.get("", response_model=list[MandateOut])
async def list_mandates(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = (
        await session.execute(
            select(Mandate)
            .where(Mandate.account_id == uuid.UUID(user["org_id"]))
            .order_by(Mandate.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return [_to_out(row) for row in rows]


@router.get("/{mandate_id}", response_model=MandateOut)
async def get_mandate(
    mandate_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return _to_out(await _owned(session, user, mandate_id))


@router.post("/{mandate_id}/activate", response_model=MandateOut)
async def activate_mandate(
    mandate_id: str,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve the mandate. This authorises later stages within its limits; it sends nothing itself."""
    row = await _owned(session, user, mandate_id)
    _transition(row, ("draft",), "active")
    if row.expires_at <= datetime.now(timezone.utc):
        row.status = "expired"
        await session.commit()
        raise HTTPException(status_code=409, detail="Mandate has expired: it was not activated")
    row.approved_at = datetime.now(timezone.utc)
    row.approved_by_user_id = uuid.UUID(user["id"])
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Another mandate is already active for this account")
    await session.refresh(row)
    return _to_out(row)


@router.post("/{mandate_id}/pause", response_model=MandateOut)
async def pause_mandate(
    mandate_id: str,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    row = await _owned(session, user, mandate_id)
    _transition(row, ("active",), "paused")
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.post("/{mandate_id}/resume", response_model=MandateOut)
async def resume_mandate(
    mandate_id: str,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    row = await _owned(session, user, mandate_id)
    _transition(row, ("paused",), "active")
    if row.expires_at <= datetime.now(timezone.utc):
        row.status = "expired"
        await session.commit()
        raise HTTPException(status_code=409, detail="Mandate has expired: it was not resumed")
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Another mandate is already active for this account")
    await session.refresh(row)
    return _to_out(row)


@router.post("/{mandate_id}/revoke", response_model=MandateOut)
async def revoke_mandate(
    mandate_id: str,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Immediate stop: no later stage may use a revoked mandate."""
    row = await _owned(session, user, mandate_id)
    if row.status != "revoked":
        row.status = "revoked"
        await session.commit()
        await session.refresh(row)
    return _to_out(row)


class LiveCounts(BaseModel):
    leads_discovered: int = 0
    duplicates_excluded: int = 0
    leads_qualified: int = 0
    hot_leads: int = 0
    errors: int = 0
    discovery_in_progress: bool = False


class LiveEvent(BaseModel):
    id: str
    action: str
    at: datetime
    detail: Optional[str] = None


class LiveOut(BaseModel):
    version: str
    changed: bool = True
    mandate_id: Optional[str] = None
    status: Optional[str] = None
    paused: bool = False
    stopped: bool = False
    latest_batch: Optional[dict] = None
    counts: Optional[LiveCounts] = None
    events: list[LiveEvent] = Field(default_factory=list)
    streams: dict = Field(default_factory=dict)


async def _mandate_hot_leads(session: AsyncSession, account_id, mandate_id) -> list:
    return [
        row for row in (
            await session.execute(
                select(ProspectingBatchItem.lead_id)
                .join(ProspectingBatch, ProspectingBatchItem.batch_id == ProspectingBatch.id)
                .where(
                    ProspectingBatch.account_id == account_id,
                    ProspectingBatch.config["mandate_id"].astext == str(mandate_id),
                    ProspectingBatchItem.stage == "hot",
                )
            )
        ).scalars().all()
        if row is not None
    ]


async def _draft_stream(session: AsyncSession, account_id, hot_leads: list) -> dict:
    """Real draft-job statuses for this mandate's Hot Leads; no fabricated zero for an unwired stream."""
    counts = {status: 0 for status in DRAFT_JOB_STATUSES}
    if hot_leads:
        rows = (
            await session.execute(
                select(DraftJob.status, func.count(DraftJob.id))
                .where(DraftJob.account_id == account_id, DraftJob.lead_id.in_(hot_leads))
                .group_by(DraftJob.status)
            )
        ).all()
        for status, total in rows:
            if status in counts:
                counts[status] = int(total)
    return {"available": True, **counts, "total": sum(counts.values())}


def _aggregate_batches(batches: list[ProspectingBatch]) -> dict:
    """Sum only counters that the discovery engine really wrote; never manufacture a zero for an unwired stream."""
    counts = {
        "leads_discovered": 0,
        "duplicates_excluded": 0,
        "leads_qualified": 0,
        "hot_leads": 0,
        "errors": 0,
        "discovery_in_progress": False,
    }
    for batch in batches:
        counters = batch.counters or {}
        reasons = batch.exclusion_reasons or {}
        counts["leads_discovered"] += int(counters.get("entities", 0))
        counts["duplicates_excluded"] += int(counters.get("duplicates_merged", 0)) + int(reasons.get("duplicate", 0))
        counts["leads_qualified"] += int(counters.get("qualified_strict", 0))
        counts["hot_leads"] += int(counters.get("hot", 0))
        counts["errors"] += int(counters.get("failed", 0)) + (1 if batch.error_summary else 0)
        counts["discovery_in_progress"] |= batch.status in ("queued", "discovering", "enriching", "qualifying")
    return counts


def _batch_out(row: ProspectingBatch) -> BatchOut:
    return BatchOut(
        id=str(row.id),
        status=row.status,
        counters=row.counters or {},
        exclusion_reasons=row.exclusion_reasons or {},
        error_summary=row.error_summary,
        checkpoint=row.checkpoint or {},
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


@router.get("/{mandate_id}/batches", response_model=list[BatchOut])
async def list_mandate_batches(
    mandate_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Real discovery progress for this mandate. No batch exists until a bounded run actually happened."""
    mandate = await _owned(session, user, mandate_id)
    rows = (
        await session.execute(
            select(ProspectingBatch)
            .where(
                ProspectingBatch.account_id == mandate.account_id,
                ProspectingBatch.config["mandate_id"].astext == str(mandate.id),
            )
            .order_by(desc(ProspectingBatch.created_at))
            .limit(50)
        )
    ).scalars().all()
    return [_batch_out(row) for row in rows]


@router.get("/{mandate_id}/batches/{batch_id}/items", response_model=list[BatchItemOut])
async def list_batch_items(
    mandate_id: str,
    batch_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Staged items with their source provenance. Another account's batch is indistinguishable from an unknown one."""
    mandate = await _owned(session, user, mandate_id)
    try:
        identifier = uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch = await session.scalar(
        select(ProspectingBatch).where(
            ProspectingBatch.id == identifier,
            ProspectingBatch.account_id == mandate.account_id,
            ProspectingBatch.config["mandate_id"].astext == str(mandate.id),
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    rows = (
        await session.execute(
            select(ProspectingBatchItem)
            .where(ProspectingBatchItem.batch_id == batch.id, ProspectingBatchItem.account_id == mandate.account_id)
            .order_by(ProspectingBatchItem.created_at)
            .limit(200)
        )
    ).scalars().all()
    return [
        BatchItemOut(
            id=str(row.id),
            name=row.name,
            category=row.category,
            stage=row.stage,
            exclusion_reason=row.exclusion_reason,
            data=row.data or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{mandate_id}/live", response_model=LiveOut)
async def mandate_live(
    mandate_id: str,
    since: Optional[str] = Query(None, description="ISO timestamp returned as `version` by the previous snapshot"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Incremental live snapshot for one mandate.

    `since` makes an unchanged poll nearly free: the server still checks ownership and the version, but does not
    recompute counters or read events. The client keeps what it already has. No artificial delay, no global poll.
    """
    mandate = await _owned(session, user, mandate_id)
    hot_leads = await _mandate_hot_leads(session, mandate.account_id, mandate.id)
    scope = (
        ProspectingBatch.account_id == mandate.account_id,
        ProspectingBatch.config["mandate_id"].astext == str(mandate.id),
    )
    bounds = await session.execute(
        select(func.max(ProspectingBatch.created_at), func.max(ProspectingBatch.updated_at)).where(*scope)
    )
    created_max, updated_max = bounds.one()
    version = max(mandate.updated_at, created_max or mandate.updated_at, updated_max or mandate.updated_at)
    if hot_leads:
        draft_latest = await session.scalar(
            select(func.max(DraftJob.updated_at)).where(
                DraftJob.account_id == mandate.account_id, DraftJob.lead_id.in_(hot_leads)
            )
        )
        send_latest = await session.scalar(
            select(func.max(OutboundMessage.updated_at)).where(
                OutboundMessage.account_id == mandate.account_id, OutboundMessage.lead_id.in_(hot_leads)
            )
        )
        version = max(version, draft_latest or version, send_latest or version)
    if since:
        try:
            previous = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="since must be an ISO timestamp")
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        if previous >= version:
            return LiveOut(version=version.isoformat(), changed=False, mandate_id=str(mandate.id))

    batches = (
        await session.execute(select(ProspectingBatch).where(*scope).order_by(desc(ProspectingBatch.created_at)).limit(100))
    ).scalars().all()
    events = (
        await session.execute(
            select(AuditLog)
            .where(
                AuditLog.account_id == mandate.account_id,
                AuditLog.resource_type == "mandate",
                AuditLog.resource_id == mandate.id,
            )
            .order_by(desc(AuditLog.created_at))
            .limit(8)
        )
    ).scalars().all()
    latest = batches[0] if batches else None
    return LiveOut(
        version=version.isoformat(),
        changed=True,
        mandate_id=str(mandate.id),
        status=mandate.status,
        paused=mandate.status == "paused",
        stopped=mandate.status in ("revoked", "expired"),
        latest_batch={
            "id": str(latest.id),
            "status": latest.status,
            "created_at": latest.created_at.isoformat(),
            "error_summary": latest.error_summary,
        } if latest is not None else None,
        counts=LiveCounts(**_aggregate_batches(batches)),
        events=[
            LiveEvent(
                id=str(row.id),
                action=row.action,
                at=row.created_at,
                detail=str((row.diff or {}).get("idempotency_key") or "")[:120] or None,
            )
            for row in events
        ],
        streams={
            "drafts": await _draft_stream(session, mandate.account_id, hot_leads),
            **await mandate_send.live_streams(session, mandate, datetime.now(timezone.utc)),
        },
    )
