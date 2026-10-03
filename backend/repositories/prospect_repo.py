"""Prospects discovered by OutreachOS: provenance, signals, scores, review, erasure.

A prospect is a `leads` row with `review_status` set. Provenance, signals and scores are append-only;
the only mutation of them is the erasure path (`erase`), which blanks personal content.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Subquery, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Contact,
    Lead,
    MessageDraft,
    OutboundEvent,
    OutboundMessage,
    ProspectScore,
    ProspectSignal,
    ProspectSource,
    ScoreVersion,
)
from repositories import consent_repo, lead_repo, suppression_repo
from services.outreach_os.normalize import normalize_email, normalize_phone
from services.outreach_os.scoring import ScoreConfig, ScoreResult
from services.outreach_os.types import Candidate, RawListing, SignalResult

ACTIVE = Lead.deleted_at.is_(None)
IN_DISCOVERY = Lead.review_status.is_not(None)


# ------------------------------------------------------------------ score versions
async def active_score_version(session: AsyncSession, account_id: uuid.UUID) -> Optional[ScoreVersion]:
    return (
        await session.execute(
            select(ScoreVersion)
            .where(ScoreVersion.account_id == account_id)
            .order_by(ScoreVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_score_version(
    session: AsyncSession, account_id: uuid.UUID, config: ScoreConfig, user_id: Optional[uuid.UUID] = None
) -> ScoreVersion:
    """Append a new configuration version (no-op returning the active one if nothing changed)."""
    current = await active_score_version(session, account_id)
    if current and current.config_hash == config.config_hash:
        return current
    version = ScoreVersion(
        account_id=account_id,
        version=(current.version + 1) if current else 1,
        label=config.label,
        config=config.canonical(),
        config_hash=config.config_hash,
        created_by_user_id=user_id,
    )
    session.add(version)
    await session.flush()
    return version


def config_of(version: ScoreVersion) -> ScoreConfig:
    return ScoreConfig(label=version.label, **version.config)


# ------------------------------------------------------------------ discovery writes
async def find_by_keys(session: AsyncSession, account_id: uuid.UUID, keys: list[str]) -> Optional[Lead]:
    if not keys:
        return None
    return (
        await session.execute(
            select(Lead)
            .where(Lead.account_id == account_id, ACTIVE, IN_DISCOVERY, Lead.match_keys.overlap(keys))
            .order_by(Lead.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_from_candidate(
    session: AsyncSession,
    account_id: uuid.UUID,
    cand: Candidate,
    *,
    vertical: str,
    source_name: str,
    country: str = "FR",
    language: str = "fr",
) -> Lead:
    listing = cand.listing
    lead, _extra = await lead_repo.create_lead(
        session,
        account_id,
        {
            "full_name": listing.name,
            "company": listing.name,
            "email": cand.email,
            "phone": cand.phone or listing.phone,
            "country": country,
            "language": language,
            "vertical": vertical,
            "city": listing.city,
            "website": listing.website,
            "match_keys": cand.match_keys,
            "review_status": "pending",
            "tags": [vertical],
            "source": source_name,
        },
    )
    return lead


async def merge_keys(session: AsyncSession, lead: Lead, keys: list[str]) -> None:
    merged = sorted(set(lead.match_keys) | set(keys))
    if merged != sorted(lead.match_keys):
        lead.match_keys = merged
        await session.flush()


def _fields_of(listing: RawListing) -> dict:
    data = asdict(listing)
    data["last_updated"] = listing.last_updated.isoformat() if listing.last_updated else None
    for key in ("lat", "lon"):  # absent, not null, so rows (and hashes) of coordinate-less sources stay as they were
        if data[key] is None:
            del data[key]
    return data


async def add_source(
    session: AsyncSession, account_id: uuid.UUID, lead_id: uuid.UUID, listing: RawListing, license_note: str
) -> tuple[ProspectSource, bool]:
    """Record one listing version. Re-ingesting identical content returns the existing row (created=False)."""
    fields = _fields_of(listing)
    content_hash = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    stmt = (
        pg_insert(ProspectSource)
        .values(
            account_id=account_id,
            lead_id=lead_id,
            source_name=listing.source_name,
            source_url=listing.source_url,
            external_id=listing.external_id,
            license_note=license_note,
            content_hash=content_hash,
            fields=fields,
        )
        .on_conflict_do_nothing(index_elements=["account_id", "source_name", "external_id", "content_hash"])
        .returning(ProspectSource.id)
    )
    created = (await session.execute(stmt)).scalar_one_or_none() is not None
    row = (
        await session.execute(
            select(ProspectSource).where(
                ProspectSource.account_id == account_id,
                ProspectSource.source_name == listing.source_name,
                ProspectSource.external_id == listing.external_id,
                ProspectSource.content_hash == content_hash,
            )
        )
    ).scalar_one()
    return row, created


async def current_signals(session: AsyncSession, lead_id: uuid.UUID) -> list[ProspectSignal]:
    """Latest observation per signal key."""
    rows = await session.execute(
        select(ProspectSignal)
        .where(ProspectSignal.lead_id == lead_id)
        .distinct(ProspectSignal.signal_key)
        .order_by(ProspectSignal.signal_key, ProspectSignal.created_at.desc(), ProspectSignal.id)
    )
    return list(rows.scalars())


async def append_signals(
    session: AsyncSession,
    account_id: uuid.UUID,
    lead_id: uuid.UUID,
    results: list[SignalResult],
    source_id: Optional[uuid.UUID],
) -> int:
    """Append only observations that differ from the current one. Returns how many rows were added."""
    latest = {s.signal_key: s for s in await current_signals(session, lead_id)}
    added = 0
    for result in results:
        prev = latest.get(result.key)
        if prev and prev.state == result.state.value and prev.evidence == result.evidence:
            continue
        session.add(
            ProspectSignal(
                account_id=account_id,
                lead_id=lead_id,
                source_id=source_id,
                signal_key=result.key,
                state=result.state.value,
                evidence=result.evidence,
            )
        )
        added += 1
    await session.flush()
    return added


async def latest_score(session: AsyncSession, lead_id: uuid.UUID) -> Optional[ProspectScore]:
    return (
        await session.execute(
            select(ProspectScore)
            .where(ProspectScore.lead_id == lead_id)
            .order_by(ProspectScore.created_at.desc(), ProspectScore.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def append_score(
    session: AsyncSession, account_id: uuid.UUID, lead_id: uuid.UUID, version: ScoreVersion, result: ScoreResult
) -> Optional[ProspectScore]:
    """Append a score unless the latest one is identical (same version and numbers). None means unchanged."""
    breakdown = result.to_breakdown()
    prev = await latest_score(session, lead_id)
    if prev and prev.score_version_id == version.id and prev.score == result.score and prev.breakdown == breakdown:
        return None
    row = ProspectScore(
        account_id=account_id,
        lead_id=lead_id,
        score_version_id=version.id,
        score=result.score,
        coverage=result.coverage,
        breakdown=breakdown,
    )
    session.add(row)
    await session.flush()
    return row


# ------------------------------------------------------------------ reads
def _latest_scores_subquery() -> Subquery:
    return (
        select(
            ProspectScore.lead_id.label("lead_id"),
            ProspectScore.score.label("score"),
            ProspectScore.coverage.label("coverage"),
            ProspectScore.score_version_id.label("score_version_id"),
        )
        .distinct(ProspectScore.lead_id)
        .order_by(ProspectScore.lead_id, ProspectScore.created_at.desc(), ProspectScore.id)
        .subquery()
    )


async def list_prospects(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    review_status: Optional[str] = None,
    min_score: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Lead, Optional[int], Optional[float]]], int]:
    latest = _latest_scores_subquery()
    conditions = [Lead.account_id == account_id, ACTIVE, IN_DISCOVERY]
    if review_status:
        conditions.append(Lead.review_status == review_status)
    if min_score is not None:
        conditions.append(latest.c.score >= min_score)
    base = select(Lead, latest.c.score, latest.c.coverage).outerjoin(latest, latest.c.lead_id == Lead.id)
    rows = await session.execute(
        base.where(*conditions)
        .order_by(latest.c.score.desc().nulls_last(), Lead.created_at.desc(), Lead.id)
        .limit(limit)
        .offset(offset)
    )
    total = (
        await session.execute(
            select(func.count()).select_from(Lead).outerjoin(latest, latest.c.lead_id == Lead.id).where(*conditions)
        )
    ).scalar_one()
    return [(lead, score, coverage) for lead, score, coverage in rows.all()], int(total)


async def get(session: AsyncSession, account_id: uuid.UUID, lead_id: str) -> Optional[Lead]:
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        return None
    return (
        await session.execute(select(Lead).where(Lead.id == lid, Lead.account_id == account_id, ACTIVE, IN_DISCOVERY))
    ).scalar_one_or_none()


async def get_any(session: AsyncSession, account_id: uuid.UUID, lead_id: str) -> Optional[Lead]:
    """A lead of this organisation, discovery or not (an unsubscribe link must work for every lead we e-mailed)."""
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        return None
    return (
        await session.execute(select(Lead).where(Lead.id == lid, Lead.account_id == account_id, ACTIVE))
    ).scalar_one_or_none()


async def fill_email(session: AsyncSession, account_id: uuid.UUID, lead: Lead, email: str) -> bool:
    """Set a missing e-mail found on the business's own site (refused if suppressed or another lead's)."""
    if lead.email or await suppression_repo.is_suppressed(session, account_id, email=email):
        return False
    taken = await session.execute(
        select(Lead.id).where(Lead.account_id == account_id, Lead.email == email, Lead.id != lead.id, ACTIVE)
    )
    if taken.first() is not None:
        return False
    lead.email = email
    await session.flush()
    return True


async def sources_of(session: AsyncSession, lead_id: uuid.UUID) -> list[ProspectSource]:
    rows = await session.execute(
        select(ProspectSource).where(ProspectSource.lead_id == lead_id).order_by(ProspectSource.created_at)
    )
    return list(rows.scalars())


async def score_version_by_id(session: AsyncSession, version_id: uuid.UUID) -> Optional[ScoreVersion]:
    return (await session.execute(select(ScoreVersion).where(ScoreVersion.id == version_id))).scalar_one_or_none()


# ------------------------------------------------------------------ review
async def set_review(
    session: AsyncSession, lead: Lead, *, status: str, user_id: uuid.UUID, note: Optional[str] = None
) -> Lead:
    lead.review_status = status
    lead.reviewed_at = datetime.now(timezone.utc)
    lead.reviewed_by_user_id = user_id
    if note:
        lead.notes = note
    await session.flush()
    return lead


# ------------------------------------------------------------------ opt-out and erasure
async def _identities(session: AsyncSession, lead: Lead) -> dict[str, str]:
    """Every identity we hold for a lead, normalised, before anything is blanked."""
    found: dict[str, str] = {}
    contacts = (await session.execute(select(Contact).where(Contact.lead_id == lead.id))).scalars().all()
    for email in {normalize_email(lead.email), *(normalize_email(c.email) for c in contacts)} - {None}:
        found[f"email:{email}"] = email  # type: ignore[assignment]
    for phone in {normalize_phone(lead.phone), *(normalize_phone(c.phone) for c in contacts)} - {None}:
        found[f"phone:{phone}"] = phone  # type: ignore[assignment]
    for key in lead.match_keys:
        if key.startswith("domain:"):
            found[key] = key.split(":", 1)[1]
    return found


async def opt_out(session: AsyncSession, account_id: uuid.UUID, lead: Lead, *, source: str) -> int:
    """Stop all contact: suppress email/phone/domain for this organisation and record an e-mail opt-out. Idempotent."""
    added = 0
    for key, value in (await _identities(session, lead)).items():
        kind = key.split(":", 1)[0]
        if await suppression_repo.add(session, account_id, kind, value, reason="opt_out"):
            added += 1
    contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
    if contact_id is not None:
        await consent_repo.record_consent(
            session, account_id, contact_id, channel="email", status="opted_out", source=source
        )
    return added


async def erase(session: AsyncSession, account_id: uuid.UUID, lead: Lead) -> None:
    """Right to erasure: suppress the identities first (so this organisation cannot rediscover them), then blank the
    personal content everywhere it was copied. Rows are kept so counts, audit and FKs stay coherent."""
    for key, value in (await _identities(session, lead)).items():
        await suppression_repo.add(session, account_id, key.split(":", 1)[0], value, reason="erasure")
    await opt_out(session, account_id, lead, source="erasure_request")  # records the consent trail

    now = datetime.now(timezone.utc)
    await session.execute(update(ProspectSource).where(ProspectSource.lead_id == lead.id).values(fields={}))
    await session.execute(update(ProspectSignal).where(ProspectSignal.lead_id == lead.id).values(evidence="[erased]"))
    await session.execute(update(ProspectScore).where(ProspectScore.lead_id == lead.id).values(breakdown=[]))
    sent_ids = select(OutboundMessage.id).where(OutboundMessage.lead_id == lead.id)
    await session.execute(update(OutboundEvent).where(OutboundEvent.message_id.in_(sent_ids)).values(detail={}))
    await session.execute(
        update(OutboundMessage)
        .where(OutboundMessage.lead_id == lead.id)
        .values(to_email=None, subject="[erased]", body="[erased]", error=None)
    )
    await session.execute(
        update(MessageDraft)
        .where(MessageDraft.lead_id == lead.id)
        .values(subject="[erased]", body="[erased]", facts=[], status="rejected")
    )
    await session.execute(
        update(Contact)
        .where(Contact.lead_id == lead.id)
        .values(full_name="[erased]", email=None, phone=None, role_title=None, deleted_at=now)
    )
    lead.full_name = "[erased]"
    lead.company = None
    lead.email = None
    lead.phone = None
    lead.website = None
    lead.notes = None
    lead.match_keys = []
    lead.review_status = "rejected"
    lead.deleted_at = now
    await session.flush()
