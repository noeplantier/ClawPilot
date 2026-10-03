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
    SignalDismissal,
)
from repositories import consent_repo, lead_repo, suppression_repo
from services.outreach_os.normalize import normalize_email, normalize_phone
from services.outreach_os.scoring import ScoreConfig, ScoreResult
from services.outreach_os.types import Candidate, RawListing, SignalResult, SignalState

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
    for key in (
        "lat",
        "lon",
        "raw",
    ):  # absent, not null, so rows (and hashes) of coordinate-less sources stay as they were
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


async def dismissals_in_force(session: AsyncSession, lead_id: uuid.UUID) -> dict[str, str]:
    """signal_key -> reason, for the signals a reviewer has dismissed and not restored."""
    rows = await session.execute(
        select(SignalDismissal)
        .where(SignalDismissal.lead_id == lead_id)
        .distinct(SignalDismissal.signal_key)
        .order_by(SignalDismissal.signal_key, SignalDismissal.created_at.desc(), SignalDismissal.id)
    )
    return {d.signal_key: d.reason or "" for d in rows.scalars() if d.action == "dismiss"}


async def add_dismissal(
    session: AsyncSession,
    account_id: uuid.UUID,
    lead_id: uuid.UUID,
    signal_key: str,
    action: str,
    reason: Optional[str],
    user_id: Optional[uuid.UUID],
) -> SignalDismissal:
    row = SignalDismissal(
        account_id=account_id,
        lead_id=lead_id,
        signal_key=signal_key,
        action=action,
        reason=reason,
        actor_user_id=user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def effective_results(session: AsyncSession, lead_id: uuid.UUID) -> list[SignalResult]:
    """The current signals as scoring and drafts must read them: reviewer dismissals applied (as UNKNOWN)."""
    from services.outreach_os.signals import apply_dismissals

    stored = await current_signals(session, lead_id)
    results = [SignalResult(s.signal_key, SignalState(s.state), s.evidence) for s in stored]
    return apply_dismissals(results, await dismissals_in_force(session, lead_id))


async def rescore_lead(
    session: AsyncSession, account_id: uuid.UUID, lead: Lead, user_id: Optional[uuid.UUID]
) -> tuple[ProspectScore, ScoreVersion]:
    """Recompute a prospect's score from its stored signals (dismissals applied) with the active configuration."""
    from services.outreach_os.scoring import compute_score

    version = await active_score_version(session, account_id)
    if version is None:
        version = await create_score_version(session, account_id, ScoreConfig(), user_id)
    await append_score(
        session,
        account_id,
        lead.id,
        version,
        compute_score(await effective_results(session, lead.id), config_of(version)),
    )
    row = await latest_score(session, lead.id)
    assert row is not None
    return row, version


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


async def detected_by_lead(session: AsyncSession, account_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    """lead_id -> signal keys currently detected, a reviewer-dismissed signal not counting (it reads as unknown)."""
    signals = await session.execute(
        select(ProspectSignal.lead_id, ProspectSignal.signal_key, ProspectSignal.state)
        .join(Lead, Lead.id == ProspectSignal.lead_id)
        .where(ProspectSignal.account_id == account_id, Lead.deleted_at.is_(None), IN_DISCOVERY)
        .distinct(ProspectSignal.lead_id, ProspectSignal.signal_key)
        .order_by(
            ProspectSignal.lead_id, ProspectSignal.signal_key, ProspectSignal.created_at.desc(), ProspectSignal.id
        )
    )
    dismissals = await session.execute(
        select(SignalDismissal.lead_id, SignalDismissal.signal_key, SignalDismissal.action)
        .where(SignalDismissal.account_id == account_id)
        .distinct(SignalDismissal.lead_id, SignalDismissal.signal_key)
        .order_by(
            SignalDismissal.lead_id, SignalDismissal.signal_key, SignalDismissal.created_at.desc(), SignalDismissal.id
        )
    )
    dismissed = {(lid, key) for lid, key, action in dismissals.all() if action == "dismiss"}
    out: dict[uuid.UUID, list[str]] = {}
    for lid, key, state in signals.all():
        if state == "detected" and (lid, key) not in dismissed:
            out.setdefault(lid, []).append(key)
    return out


async def list_positions(session: AsyncSession, account_id: uuid.UUID, limit: int = 2000) -> list[dict]:
    """Discovery prospects whose latest source carries a position (lat/lon), for the map. Newest first."""
    latest = _latest_scores_subquery()
    detected = await detected_by_lead(session, account_id)
    ranked = (
        select(
            ProspectSource.lead_id,
            ProspectSource.fields,
            func.row_number()
            .over(partition_by=ProspectSource.lead_id, order_by=ProspectSource.created_at.desc())
            .label("rn"),
        )
        .where(ProspectSource.account_id == account_id)
        .subquery()
    )
    rows = await session.execute(
        select(Lead, ranked.c.fields, latest.c.score)
        .join(ranked, ranked.c.lead_id == Lead.id)
        .outerjoin(latest, latest.c.lead_id == Lead.id)
        .where(ranked.c.rn == 1, Lead.account_id == account_id, ACTIVE, IN_DISCOVERY)
        .order_by(Lead.created_at.desc())
        .limit(limit * 2)
    )
    out: list[dict] = []
    for lead, fields, score in rows.all():
        lat, lon = fields.get("lat"), fields.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append(
                {
                    "id": str(lead.id),
                    "name": lead.full_name,
                    "city": lead.city,
                    "lat": float(lat),
                    "lon": float(lon),
                    "review_status": lead.review_status,
                    "has_email": bool(lead.email),
                    "external_id": fields.get("external_id"),
                    "vertical": lead.vertical,
                    "country": lead.country,
                    "score": score,  # None = not scored, never 0
                    "signals": sorted(detected.get(lead.id, [])),
                    "created_at": lead.created_at,
                }
            )
    return out[:limit]


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
    await session.execute(update(SignalDismissal).where(SignalDismissal.lead_id == lead.id).values(reason=None))
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
