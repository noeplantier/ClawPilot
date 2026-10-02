"""OutreachOS prospects: discovery (dry-run), review queue, score explanation, drafts, opt-out, erasure.

Thin routes: logic lives in services/outreach_os and repositories/. Nothing here sends a message.
Reading is open to any member; every action that changes state or decides on a prospect needs owner/admin.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, Lead, MessageDraft, ScoreVersion
from db.session import get_db_session
from deps import JWT_SECRET, get_current_user, require_roles
from models import (
    DiscoveryRunIn,
    DiscoveryRunOut,
    DraftOut,
    OutreachSettingsOut,
    ProspectDetail,
    ProspectEventOut,
    ProspectList,
    ProspectSummary,
    ReviewIn,
    ScoreConfigIO,
    ScoreConfigOut,
    ScoreOut,
    SignalOut,
    SourceOut,
    SuppressionIn,
    SuppressionOut,
)
from repositories import (
    audit_repo,
    consent_repo,
    draft_repo,
    outbound_repo,
    prospect_repo,
    suppression_repo,
    usage_repo,
)
from services import feature_flags
from services.outreach_os import drafts as drafts_svc
from services.outreach_os import pipeline
from services.outreach_os import signals as sig
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone
from services.outreach_os.scoring import ScoreConfig
from services.outreach_os.sources import DEMO_SOURCE_NAME, FixtureDirectoryAdapter, FixtureSiteFetcher
from services.outreach_os.types import SignalResult, SignalState
from services.outreach_os.unsubscribe import make_token

router = APIRouter(prefix="/prospects", tags=["prospects"])
decider = require_roles("owner", "admin")  # who may validate, reject, erase or reconfigure


def _uid(user: dict) -> uuid.UUID:
    return uuid.UUID(user["id"])


def _account(user: dict) -> uuid.UUID:
    return uuid.UUID(user["org_id"])


def _summary(lead: Lead, score: Optional[int], coverage: Optional[float]) -> dict:
    return {
        "id": str(lead.id),
        "name": lead.full_name,
        "city": lead.city,
        "vertical": lead.vertical,
        "website": lead.website,
        "review_status": lead.review_status,
        "score": score,
        "coverage": coverage,
        "created_at": lead.created_at,
    }


async def _require_prospect(session: AsyncSession, user: dict, lead_id: str) -> Lead:
    lead = await prospect_repo.get(session, _account(user), lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return lead


def _draft_out(d: MessageDraft) -> DraftOut:
    return DraftOut(
        id=str(d.id),
        channel=d.channel,
        subject=d.subject,
        body=d.body,
        facts=d.facts,
        template_version=d.template_version,
        status=d.status,
        dry_run=d.dry_run,
        review_note=d.review_note,
        reviewed_at=d.reviewed_at,
        created_at=d.created_at,
    )


# ---------------------------------------------------------------- settings / configuration
@router.get("/settings", response_model=OutreachSettingsOut)
async def settings_overview(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    version = await prospect_repo.active_score_version(session, _account(user))
    return OutreachSettingsOut(
        flags=feature_flags.snapshot(),
        sender_configured=drafts_svc.SenderIdentity.from_env() is not None,
        usage=await usage_repo.totals(session, _account(user)),
        active_score_version=version.version if version else None,
    )


def _config_out(version: ScoreVersion, rescored: int = 0) -> ScoreConfigOut:
    cfg = prospect_repo.config_of(version)
    return ScoreConfigOut(
        label=cfg.label,
        weights=cfg.weights,
        stale_days=cfg.stale_days,
        version=version.version,
        config_hash=version.config_hash,
        rescored=rescored,
    )


@router.get("/score-config", response_model=ScoreConfigOut)
async def get_score_config(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    version = await prospect_repo.active_score_version(session, _account(user))
    if version is None:  # nothing stored yet: report the defaults without creating a version
        defaults = ScoreConfig()
        return ScoreConfigOut(
            label=defaults.label,
            weights=defaults.weights,
            stale_days=defaults.stale_days,
            version=0,
            config_hash=defaults.config_hash,
        )
    return _config_out(version)


@router.put("/score-config", response_model=ScoreConfigOut)
async def put_score_config(
    payload: ScoreConfigIO, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Create a new immutable score version and recompute every prospect from its stored signals.
    `stale_days` only takes effect at the next discovery run (staleness is observed there)."""
    try:
        config = ScoreConfig(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    account_id = _account(user)
    before = await prospect_repo.active_score_version(session, account_id)
    version = await prospect_repo.create_score_version(session, account_id, config, _uid(user))
    rescored = 0
    if before is None or before.id != version.id:
        rescored = await pipeline.rescore_all(session, account_id, version, config)
        await audit_repo.log(
            session,
            account_id,
            action="score_config.changed",
            resource_type="score_version",
            resource_id=version.id,
            actor_user_id=_uid(user),
            diff={"version": version.version, "config_hash": version.config_hash, "rescored": rescored},
        )
    return _config_out(version, rescored)


# ---------------------------------------------------------------- discovery
@router.post("/discovery/run", response_model=DiscoveryRunOut)
async def run_discovery(
    payload: DiscoveryRunIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Run discovery in dry-run mode against a local fixture source. No network access, nothing is sent."""
    if payload.source != DEMO_SOURCE_NAME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source '{payload.source}'. Only '{DEMO_SOURCE_NAME}' is implemented "
            "(network-backed sources are disabled by design, see docs/compliance.md).",
        )
    summary = await pipeline.run_discovery(
        session,
        _account(user),
        adapter=FixtureDirectoryAdapter(),
        fetcher=FixtureSiteFetcher(),
        now=date.today(),
        user_id=_uid(user),
    )
    return DiscoveryRunOut(dry_run=True, source=payload.source, **summary.__dict__)


# ---------------------------------------------------------------- opt-out list
@router.post("/suppressions", response_model=SuppressionOut)
async def add_suppression(
    payload: SuppressionIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Add identities to this organisation's do-not-contact list (stored hashed)."""
    account_id = _account(user)
    added = 0
    for kind, value in (
        ("email", normalize_email(payload.email)),
        ("phone", normalize_phone(payload.phone)),
        ("domain", normalize_domain(payload.domain)),
    ):
        if value and await suppression_repo.add(session, account_id, kind, value, reason="manual"):
            added += 1
    await audit_repo.log(
        session,
        account_id,
        action="suppression.added",
        resource_type="suppression",
        actor_user_id=_uid(user),
        diff={"added": added},  # never the identity itself
    )
    return SuppressionOut(added=added)


# ---------------------------------------------------------------- list / detail
@router.get("", response_model=ProspectList)
async def list_prospects(
    review_status: Optional[str] = Query(default=None, pattern="^(pending|approved|rejected)$"),
    min_score: Optional[int] = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows, total = await prospect_repo.list_prospects(
        session, _account(user), review_status=review_status, min_score=min_score, limit=limit, offset=offset
    )
    return ProspectList(items=[ProspectSummary(**_summary(*row)) for row in rows], total=total)


@router.get("/{lead_id}", response_model=ProspectDetail)
async def get_prospect(
    lead_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    lead = await _require_prospect(session, user, lead_id)
    score_row = await prospect_repo.latest_score(session, lead.id)
    score_out = None
    if score_row:
        version = await prospect_repo.score_version_by_id(session, score_row.score_version_id)
        assert version is not None
        score_out = ScoreOut(
            score=score_row.score,
            coverage=score_row.coverage,
            version=version.version,
            config_label=version.label,
            config_hash=version.config_hash,
            computed_at=score_row.created_at,
            breakdown=score_row.breakdown,
        )
    stored = await prospect_repo.current_signals(session, lead.id)
    sources = await prospect_repo.sources_of(session, lead.id)
    drafts = await draft_repo.list_for_lead(session, _account(user), lead.id)
    base = _summary(lead, score_row.score if score_row else None, score_row.coverage if score_row else None)
    return ProspectDetail(
        **base,
        contact_email=lead.email,
        contact_phone=lead.phone,
        reviewed_at=lead.reviewed_at,
        sources=[
            SourceOut(
                id=str(s.id),
                source_name=s.source_name,
                source_url=s.source_url,
                external_id=s.external_id,
                license_note=s.license_note,
                fetched_at=s.fetched_at,
                fields=s.fields,
            )
            for s in sources
        ],
        signals=[
            SignalOut(
                key=s.signal_key,
                label=sig.SIGNAL_LABELS.get(s.signal_key, s.signal_key),
                state=s.state,
                evidence=s.evidence,
                observed_at=s.created_at,
            )
            for s in stored
        ],
        score_detail=score_out,
        drafts=[_draft_out(d) for d in drafts],
    )


# ---------------------------------------------------------------- human review
@router.post("/{lead_id}/review", response_model=ProspectSummary)
async def review_prospect(
    lead_id: str, payload: ReviewIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    lead = await _require_prospect(session, user, lead_id)
    new_status = "approved" if payload.decision == "approve" else "rejected"
    if payload.decision == "approve" and await suppression_repo.is_suppressed(
        session,
        _account(user),
        email=normalize_email(lead.email),
        phone=normalize_phone(lead.phone),
        domain=normalize_domain(lead.website),
    ):
        raise HTTPException(status_code=409, detail="Prospect is on the suppression list and cannot be approved")
    previous = lead.review_status
    await prospect_repo.set_review(session, lead, status=new_status, user_id=_uid(user), note=payload.note)
    await audit_repo.log(
        session,
        _account(user),
        action=f"prospect.{new_status}",
        resource_type="prospect",
        resource_id=lead.id,
        actor_user_id=_uid(user),
        diff={"from": previous, "to": new_status, "has_note": bool(payload.note)},
    )
    score_row = await prospect_repo.latest_score(session, lead.id)
    return ProspectSummary(
        **_summary(lead, score_row.score if score_row else None, score_row.coverage if score_row else None)
    )


@router.post("/{lead_id}/rescore", response_model=ScoreOut)
async def rescore_prospect(
    lead_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Recompute from the stored signals with the active configuration (no new observation is made)."""
    from services.outreach_os.scoring import compute_score

    lead = await _require_prospect(session, user, lead_id)
    account_id = _account(user)
    version = await prospect_repo.active_score_version(session, account_id)
    if version is None:
        version = await prospect_repo.create_score_version(session, account_id, ScoreConfig(), _uid(user))
    stored = await prospect_repo.current_signals(session, lead.id)
    results = [SignalResult(s.signal_key, SignalState(s.state), s.evidence) for s in stored]
    result = compute_score(results, prospect_repo.config_of(version))
    await prospect_repo.append_score(session, account_id, lead.id, version, result)
    row = await prospect_repo.latest_score(session, lead.id)
    assert row is not None
    return ScoreOut(
        score=row.score,
        coverage=row.coverage,
        version=version.version,
        config_label=version.label,
        config_hash=version.config_hash,
        computed_at=row.created_at,
        breakdown=row.breakdown,
    )


# ---------------------------------------------------------------- drafts
def _public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


@router.post("/{lead_id}/drafts", response_model=DraftOut)
async def create_draft(
    lead_id: str,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=200),
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Prepare (never send) an e-mail draft for an approved prospect. Same key ⇒ same draft, no duplicate."""
    lead = await _require_prospect(session, user, lead_id)
    account_id = _account(user)
    if lead.review_status != "approved":
        raise HTTPException(status_code=409, detail="Prospect must be approved before a draft is prepared")
    if not lead.email:
        raise HTTPException(status_code=422, detail="This prospect has no public e-mail address")
    if await suppression_repo.is_suppressed(
        session,
        account_id,
        email=normalize_email(lead.email),
        phone=normalize_phone(lead.phone),
        domain=normalize_domain(lead.website),
    ):
        raise HTTPException(status_code=409, detail="Prospect is on the suppression list")
    contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
    if contact_id is not None:
        status = await consent_repo.get_status(session, contact_id, "email")
        if not consent_repo.can_send("email", status):
            raise HTTPException(status_code=409, detail="Prospect opted out of e-mail")
    sender = drafts_svc.SenderIdentity.from_env()
    if sender is None:
        raise HTTPException(
            status_code=409,
            detail="Sender identity is not configured (OUTREACH_SENDER_NAME, _COMPANY, _ADDRESS, _EMAIL)",
        )

    version = await prospect_repo.active_score_version(session, account_id)
    sources = await prospect_repo.sources_of(session, lead.id)
    if not sources:
        raise HTTPException(status_code=409, detail="Prospect has no recorded source")
    source = max(sources, key=lambda s: s.fields.get("last_updated") or "")
    stored = await prospect_repo.current_signals(session, lead.id)
    results = [SignalResult(s.signal_key, SignalState(s.state), s.evidence) for s in stored]
    last_updated = date.fromisoformat(source.fields["last_updated"]) if source.fields.get("last_updated") else None
    token = make_token(JWT_SECRET, account_id, lead.id)
    content = drafts_svc.render_email_draft(
        business_name=lead.full_name,
        city=lead.city,
        results=results,
        source_name=source.source_name,
        last_updated=last_updated,
        sender=sender,
        unsubscribe_url=f"{_public_base_url()}/api/unsubscribe/{token}",
    )
    key = (
        idempotency_key
        or hashlib.sha256(
            f"{lead.id}|{version.id if version else ''}|{content.template_version}|email".encode()
        ).hexdigest()
    )
    draft, created = await draft_repo.create_idempotent(
        session,
        account_id,
        idempotency_key=key,
        lead_id=lead.id,
        channel="email",
        subject=content.subject,
        body=content.body,
        facts=content.facts,
        template_version=content.template_version,
        status="draft",
        dry_run=feature_flags.dry_run(),
        created_by_user_id=_uid(user),
    )
    if created:
        await usage_repo.record(session, account_id, "drafts_generated", 1)
        await audit_repo.log(
            session,
            account_id,
            action="draft.created",
            resource_type="draft",
            resource_id=draft.id,
            actor_user_id=_uid(user),
            diff={"prospect_id": str(lead.id), "dry_run": draft.dry_run, "facts": len(content.facts)},
        )
    return _draft_out(draft)


@router.post("/drafts/{draft_id}/review", response_model=DraftOut)
async def review_draft(
    draft_id: str, payload: ReviewIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Human validation of a draft. Approval is refused if mandatory elements (sender identity, data origin,
    unsubscribe link) are missing. An approved draft is still not sent: dry-run, no channel adapter yet."""
    account_id = _account(user)
    draft = await draft_repo.get(session, account_id, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status != "draft":
        raise HTTPException(status_code=409, detail=f"Draft already {draft.status}")
    new_status = "approved" if payload.decision == "approve" else "rejected"
    if new_status == "approved":
        sender = drafts_svc.SenderIdentity.from_env()
        if sender is None:
            raise HTTPException(status_code=409, detail="Sender identity is not configured")
        problems = drafts_svc.compliance_problems(draft.body, sender)
        if problems:
            raise HTTPException(status_code=422, detail=f"Draft is not compliant: {', '.join(problems)}")
    await draft_repo.review(session, draft, status=new_status, user_id=_uid(user), note=payload.note)
    await audit_repo.log(
        session,
        account_id,
        action=f"draft.{new_status}",
        resource_type="draft",
        resource_id=draft.id,
        actor_user_id=_uid(user),
        diff={"prospect_id": str(draft.lead_id), "dry_run": draft.dry_run},
    )
    return _draft_out(draft)


# ---------------------------------------------------------------- history / erasure
@router.get("/{lead_id}/events", response_model=list[ProspectEventOut])
async def prospect_events(
    lead_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Audit history of this prospect, its drafts and its dispatched messages, newest first."""
    lead = await _require_prospect(session, user, lead_id)
    draft_ids = [d.id for d in await draft_repo.list_for_lead(session, _account(user), lead.id)]
    message_ids = await outbound_repo.ids_for_lead(session, _account(user), lead.id)
    rows = await session.execute(
        select(AuditLog)
        .where(AuditLog.account_id == _account(user), AuditLog.resource_id.in_([lead.id, *draft_ids, *message_ids]))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        ProspectEventOut(
            id=str(r.id),
            action=r.action,
            actor_type=r.actor_type,
            actor_user_id=str(r.actor_user_id) if r.actor_user_id else None,
            detail=r.diff or {},
            created_at=r.created_at,
        )
        for r in rows.scalars()
    ]


@router.post("/{lead_id}/erase", status_code=204, response_class=Response)
async def erase_prospect(
    lead_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
) -> Response:
    """Right to erasure: blank personal content everywhere and suppress the identities for this organisation."""
    lead = await _require_prospect(session, user, lead_id)
    await prospect_repo.erase(session, _account(user), lead)
    await audit_repo.log(
        session,
        _account(user),
        action="prospect.erased",
        resource_type="prospect",
        resource_id=lead.id,
        actor_user_id=_uid(user),
        diff={},
    )
    return Response(status_code=204)
