"""Lead persistence. Translates between the stable HTTP contract (plain
`source: str`, `tags: list[str]`) and the relational storage (`lead_sources`
FK, `tags` array column, `contacts`/`consent_current` for opt-in tracking) —
see plan doc section 1.3/1.4/1.6/1.7.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Contact, Lead, LeadScore, LeadSource, OutreachEvent
from repositories import consent_repo
from services import feature_flags, scoring

ACTIVE = Lead.deleted_at.is_(None)


@dataclass
class LeadExtra:
    """Fields resolved from related tables, bundled alongside a `Lead` ORM row
    so routes can build the full HTTP response without extra round trips."""

    source: Optional[str] = None
    contact_id: Optional[uuid.UUID] = None
    email_consent: str = "unknown"
    whatsapp_consent: str = "unknown"


_SOURCE_NAME_TO_KIND = {
    "referral": "referral",
    "csv_upload": "csv_import",
    "csv_import": "csv_import",
    "scraper": "scraper",
    "api": "api",
    "fixture_directory": "api",
    "enrichment": "enrichment",
}


def _infer_source_kind(name: str) -> str:
    """Best-effort mapping from a free-text source name to the `lead_sources.kind`
    enum, which `services/scoring.py` uses as an intent signal — a name we don't
    recognize (e.g. 'webinar', 'linkedin') falls back to 'manual' rather than
    guessing, since the CHECK constraint only allows a fixed set of kinds."""
    return _SOURCE_NAME_TO_KIND.get(name.lower().strip(), "manual")


async def _resolve_source_id(session: AsyncSession, account_id: uuid.UUID, name: Optional[str]) -> Optional[uuid.UUID]:
    """Get-or-create a `LeadSource` row by name for this account."""
    if not name:
        return None
    result = await session.execute(
        select(LeadSource).where(LeadSource.account_id == account_id, LeadSource.name == name)
    )
    source = result.scalar_one_or_none()
    if source:
        return source.id
    source = LeadSource(account_id=account_id, name=name, kind=_infer_source_kind(name))
    session.add(source)
    await session.flush()
    return source.id


async def _create_primary_contact(
    session: AsyncSession,
    account_id: uuid.UUID,
    lead: Lead,
    *,
    email_opt_in: bool = False,
    whatsapp_opt_in: bool = False,
    consent_source: Optional[str] = None,
) -> Contact:
    """Every lead gets one primary contact at creation time — consent is tracked
    per-contact, not per-lead (plan doc section 1.6), and a lead can't have any
    consent trail at all without one."""
    contact = Contact(
        account_id=account_id,
        lead_id=lead.id,
        full_name=lead.full_name,
        email=lead.email,
        phone=lead.phone,
        is_primary=True,
    )
    session.add(contact)
    await session.flush()

    source = consent_source or "lead_import"
    if email_opt_in:
        await consent_repo.record_consent(
            session, account_id, contact.id, channel="email", status="opted_in", source=source
        )
    if whatsapp_opt_in:
        await consent_repo.record_consent(
            session, account_id, contact.id, channel="whatsapp", status="opted_in", source=source
        )
    return contact


async def load_extra(session: AsyncSession, lead: Lead) -> LeadExtra:
    source_name = None
    if lead.source_id is not None:
        result = await session.execute(select(LeadSource.name).where(LeadSource.id == lead.source_id))
        source_name = result.scalar_one_or_none()

    contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
    email_consent = "unknown"
    whatsapp_consent = "unknown"
    if contact_id:
        email_consent = await consent_repo.get_status(session, contact_id, "email")
        whatsapp_consent = await consent_repo.get_status(session, contact_id, "whatsapp")

    return LeadExtra(
        source=source_name, contact_id=contact_id, email_consent=email_consent, whatsapp_consent=whatsapp_consent
    )


@dataclass
class BulkResult:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    lead_ids: list[str] = field(default_factory=list)


async def list_leads(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    stage: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 500,
) -> list[tuple[Lead, LeadExtra]]:
    stmt = select(Lead).options(selectinload(Lead.contacts)).where(Lead.account_id == account_id, ACTIVE)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(Lead.full_name.ilike(pattern), Lead.email.ilike(pattern), Lead.company.ilike(pattern)))
    stmt = stmt.order_by(Lead.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    leads = result.scalars().all()
    return [(lead, await load_extra(session, lead)) for lead in leads]


async def create_lead(session: AsyncSession, account_id: uuid.UUID, data: dict) -> tuple[Lead, LeadExtra]:
    source_name = data.pop("source", None)
    email_opt_in = data.pop("email_opt_in", False)
    whatsapp_opt_in = data.pop("whatsapp_opt_in", False)
    consent_source = data.pop("consent_source", None)
    source_id = await _resolve_source_id(session, account_id, source_name)
    lead = Lead(account_id=account_id, source_id=source_id, **data)
    session.add(lead)
    await session.flush()
    await _create_primary_contact(
        session,
        account_id,
        lead,
        email_opt_in=email_opt_in,
        whatsapp_opt_in=whatsapp_opt_in,
        consent_source=consent_source,
    )
    await rescore_lead(session, account_id, lead)
    return lead, await load_extra(session, lead)


async def bulk_create_leads(session: AsyncSession, account_id: uuid.UUID, items: list[dict]) -> BulkResult:
    """Dedupes by email within the account (mirrors the legacy Mongo bulk import)."""
    result = BulkResult()

    existing_emails: set[str] = set()
    if any(item.get("email") for item in items):
        rows = await session.execute(
            select(Lead.email).where(Lead.account_id == account_id, ACTIVE, Lead.email.isnot(None))
        )
        existing_emails = {e.lower() for (e,) in rows if e}

    for item in items:
        try:
            email = item.get("email")
            if email and email.lower() in existing_emails:
                result.skipped += 1
                continue
            source_name = item.pop("source", None)
            email_opt_in = item.pop("email_opt_in", False)
            whatsapp_opt_in = item.pop("whatsapp_opt_in", False)
            consent_source = item.pop("consent_source", None)
            source_id = await _resolve_source_id(session, account_id, source_name)
            lead = Lead(account_id=account_id, source_id=source_id, **item)
            session.add(lead)
            await session.flush()
            await _create_primary_contact(
                session,
                account_id,
                lead,
                email_opt_in=email_opt_in,
                whatsapp_opt_in=whatsapp_opt_in,
                consent_source=consent_source,
            )
            await rescore_lead(session, account_id, lead)
            result.lead_ids.append(str(lead.id))
            if email:
                existing_emails.add(email.lower())
            result.created += 1
        except Exception as e:  # noqa: BLE001 — surfaced per-row like the legacy endpoint
            result.errors.append(f"{item.get('full_name')}: {str(e)[:80]}")

    return result


async def bulk_update_stage(session: AsyncSession, account_id: uuid.UUID, lead_ids: list[str], stage: str) -> int:
    ids = [uuid.UUID(i) for i in lead_ids]
    result = await session.execute(select(Lead).where(Lead.id.in_(ids), Lead.account_id == account_id, ACTIVE))
    leads = result.scalars().all()
    for lead in leads:
        lead.stage = stage
    return len(leads)


async def bulk_delete_leads(session: AsyncSession, account_id: uuid.UUID, lead_ids: list[str]) -> int:

    ids = [uuid.UUID(i) for i in lead_ids]
    result = await session.execute(select(Lead).where(Lead.id.in_(ids), Lead.account_id == account_id, ACTIVE))
    leads = result.scalars().all()
    for lead in leads:
        lead.deleted_at = func.now()
    return len(leads)


async def bulk_tag_leads(
    session: AsyncSession, account_id: uuid.UUID, lead_ids: list[str], tags: list[str], mode: str
) -> int:
    ids = [uuid.UUID(i) for i in lead_ids]
    result = await session.execute(select(Lead).where(Lead.id.in_(ids), Lead.account_id == account_id, ACTIVE))
    leads = result.scalars().all()
    for lead in leads:
        lead.tags = list(tags) if mode == "replace" else sorted(set(lead.tags) | set(tags))
    return len(leads)


async def update_lead(
    session: AsyncSession, account_id: uuid.UUID, lead_id: str, updates: dict
) -> Optional[tuple[Lead, LeadExtra]]:
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        return None
    result = await session.execute(select(Lead).where(Lead.id == lid, Lead.account_id == account_id, ACTIVE))
    lead = result.scalar_one_or_none()
    if not lead:
        return None
    if "source" in updates:
        updates["source_id"] = await _resolve_source_id(session, account_id, updates.pop("source"))
    for key, value in updates.items():
        setattr(lead, key, value)
    await session.flush()
    return lead, await load_extra(session, lead)


def _sendable_clause():
    """Leads from the CRM (review_status NULL) behave as before. A prospect from OutreachOS discovery is only
    reachable by the send paths once a human approved it AND live sending is enabled (never in dry-run)."""
    if feature_flags.dry_run():
        return Lead.review_status.is_(None)
    return or_(Lead.review_status.is_(None), Lead.review_status == "approved")


async def discovery_send_block(session: AsyncSession, account_id: uuid.UUID, lead_id: uuid.UUID) -> Optional[str]:
    """Why a single-recipient send must be refused for a discovery prospect, or None if it may proceed."""
    status = (
        await session.execute(select(Lead.review_status).where(Lead.id == lead_id, Lead.account_id == account_id))
    ).scalar_one_or_none()
    if status is None:
        return None
    if status != "approved":
        return f"prospect review status is '{status}'"
    return "dry-run mode: live sending is disabled" if feature_flags.dry_run() else None


async def get_leads_by_ids(session: AsyncSession, account_id: uuid.UUID, lead_ids: list[str]) -> list[dict]:
    """Plain-dict shape (id/full_name/email/phone/company/title/country/contact_id/
    *_consent) for template rendering, consent checks, and cross-domain lookups
    from not-yet-migrated routes (campaigns run-step/assign-leads, messages batch
    send) — mirrors the legacy Mongo document shape those callers already expect,
    extended with the consent fields Phase 2 needs."""
    try:
        ids = [uuid.UUID(i) for i in lead_ids]
    except ValueError:
        return []
    result = await session.execute(
        select(Lead).where(Lead.id.in_(ids), Lead.account_id == account_id, ACTIVE, _sendable_clause())
    )
    leads = result.scalars().all()
    if not leads:
        return []

    lead_by_contact_query = await session.execute(
        select(Contact.lead_id, Contact.id).where(
            Contact.lead_id.in_([lead.id for lead in leads]), Contact.is_primary.is_(True), Contact.deleted_at.is_(None)
        )
    )
    contact_by_lead: dict[uuid.UUID, uuid.UUID] = {
        lead_id: contact_id for lead_id, contact_id in lead_by_contact_query.all()
    }
    contact_ids = list(contact_by_lead.values())
    email_consents = await consent_repo.get_status_map(session, contact_ids, "email")
    whatsapp_consents = await consent_repo.get_status_map(session, contact_ids, "whatsapp")

    out = []
    for lead in leads:
        contact_id = contact_by_lead.get(lead.id)
        out.append(
            {
                "id": str(lead.id),
                "full_name": lead.full_name,
                "email": lead.email,
                "phone": lead.phone,
                "company": lead.company,
                "title": lead.title,
                "country": lead.country,
                "contact_id": str(contact_id) if contact_id else None,
                "email_consent": email_consents.get(contact_id, "unknown") if contact_id else "unknown",
                "whatsapp_consent": whatsapp_consents.get(contact_id, "unknown") if contact_id else "unknown",
            }
        )
    return out


async def count_leads(session: AsyncSession, account_id: uuid.UUID, *, country: Optional[str] = None) -> int:

    stmt = select(func.count()).select_from(Lead).where(Lead.account_id == account_id, ACTIVE)
    if country:
        stmt = stmt.where(Lead.country == country)
    result = await session.execute(stmt)
    return result.scalar_one()


async def pipeline_breakdown(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:

    result = await session.execute(
        select(Lead.stage, func.count()).where(Lead.account_id == account_id, ACTIVE).group_by(Lead.stage)
    )
    return {stage: count for stage, count in result.all()}


async def top_countries(session: AsyncSession, account_id: uuid.UUID, limit: int = 6) -> list[tuple[str, int]]:
    """Real top-N by lead count, replacing the dashboard's old fixed 6-country
    guess list (which silently showed 0 for any account whose leads are
    concentrated elsewhere)."""
    result = await session.execute(
        select(Lead.country, func.count())
        .where(Lead.account_id == account_id, ACTIVE, Lead.country.is_not(None))
        .group_by(Lead.country)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [(country, count) for country, count in result.all() if country is not None]


async def get_lead_by_phone(session: AsyncSession, phone: str) -> Optional[dict]:
    """Global (cross-account) phone lookup for inbound WhatsApp webhooks, which
    don't know the account ahead of time — mirrors the legacy unscoped Mongo query."""
    result = await session.execute(select(Lead).where(Lead.phone == phone, ACTIVE).limit(1))
    lead = result.scalar_one_or_none()
    if not lead:
        return None
    contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
    return {
        "id": str(lead.id),
        "org_id": str(lead.account_id),
        "phone": lead.phone,
        "contact_id": str(contact_id) if contact_id else None,
    }


async def get_lead(session: AsyncSession, account_id: uuid.UUID, lead_id: str) -> Optional[Lead]:
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        return None
    result = await session.execute(select(Lead).where(Lead.id == lid, Lead.account_id == account_id, ACTIVE))
    return result.scalar_one_or_none()


async def delete_lead(session: AsyncSession, account_id: uuid.UUID, lead_id: str) -> bool:

    lead = await get_lead(session, account_id, lead_id)
    if not lead:
        return False
    lead.deleted_at = func.now()
    return True


async def _gather_signals(session: AsyncSession, lead: Lead) -> scoring.LeadSignals:
    from datetime import datetime, timezone

    source_kind: Optional[str] = None
    if lead.source_id is not None:
        result = await session.execute(select(LeadSource.kind).where(LeadSource.id == lead.source_id))
        source_kind = result.scalar_one_or_none()

    counts_result = await session.execute(
        select(OutreachEvent.event_type, func.count())
        .where(OutreachEvent.lead_id == lead.id, OutreachEvent.event_type.in_(list(scoring.ENGAGEMENT_POINTS)))
        .group_by(OutreachEvent.event_type)
    )
    event_counts = {event_type: count for event_type, count in counts_result.all()}

    last_activity_result = await session.execute(
        select(func.max(OutreachEvent.occurred_at)).where(OutreachEvent.lead_id == lead.id)
    )
    last_activity = last_activity_result.scalar_one_or_none() or lead.created_at
    days_since = (datetime.now(timezone.utc) - last_activity).days

    return scoring.LeadSignals(
        title=lead.title,
        country=lead.country,
        tags=list(lead.tags),
        source_kind=source_kind,
        event_counts=event_counts,
        days_since_last_activity=days_since,
    )


async def rescore_lead(session: AsyncSession, account_id: uuid.UUID, lead: Lead, *, computed_by: str = "system") -> int:
    """Compute a fresh score for one lead, record the breakdown in `lead_scores`
    (append-only), and update the denormalized `Lead.score`."""
    signals = await _gather_signals(session, lead)
    result = scoring.compute_score(signals)
    delta = result.score - (lead.score or 0)
    reason = "; ".join(f"{f.reason} ({f.delta:+d})" for f in result.factors)

    session.add(
        LeadScore(
            lead_id=lead.id,
            account_id=account_id,
            score=result.score,
            reason=reason[:2000],
            delta=delta,
            computed_by=computed_by,
        )
    )
    lead.score = result.score
    return result.score


async def enrich_leads(session: AsyncSession, account_id: uuid.UUID) -> int:
    """Real weighted scoring pass (role/country/tags/source/engagement/decay —
    see services/scoring.py) — replaces the legacy random score bump."""
    result = await session.execute(select(Lead).where(Lead.account_id == account_id, ACTIVE))
    leads = result.scalars().all()
    for lead in leads:
        await rescore_lead(session, account_id, lead)
    return len(leads)
