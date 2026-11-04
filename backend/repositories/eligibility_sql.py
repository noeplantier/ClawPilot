"""SQL twin of services/outreach_os/eligibility.py: the same decision for ordering, pages and counters.

Every surface that must agree (map, lists, city counters, dashboard, suggestions) filters with `qualified(...)`, so a
prospect is never drawn by one and counted out by another. JSON read from a source is guarded with `jsonb_typeof` before
any cast (a malformed value is a gap, never an error). Everything is scoped by `account_id`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Float, String, Subquery, and_, case, cast, exists, false, func, literal, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from db.models import ConsentCurrent, ConsentRecord, Contact, Lead, ProspectSignal, ProspectSource, SuppressionEntry
from repositories import heat_sql
from services.outreach_os import eligibility as policy

EMAIL_RE = r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$"  # the pattern of normalize.normalize_email
PLACEHOLDER_RE = r"(^|\.)(example|invalid|test|localhost)(\.|$)"


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def is_demo_source() -> ColumnElement[bool]:
    """Durable demo provenance on a ProspectSource row (the Python `eligibility.is_demo_source`)."""
    return or_(
        ProspectSource.source_name.in_(policy.DEMO_SOURCE_NAMES),
        ProspectSource.source_url.startswith("fixture://"),
        func.lower(ProspectSource.license_note).contains("fictional data"),
        func.coalesce(ProspectSource.fields["demo_data"].astext, "") == "true",
    )


def _typed(fields: ColumnElement, key: str, kind: str) -> ColumnElement:
    return case((func.jsonb_typeof(fields[key]) == kind, fields[key].astext))


def latest_source(account_id: uuid.UUID) -> Subquery:
    """Each prospect's latest non-demo source with the address and position it published (NULL if absent/malformed)."""
    fields = ProspectSource.fields
    return (
        select(
            ProspectSource.lead_id.label("lead_id"),
            ProspectSource.id.label("source_id"),
            ProspectSource.external_id.label("external_id"),
            ProspectSource.fetched_at.label("fetched_at"),
            _typed(fields, "address", "string").label("address"),
            cast(_typed(fields, "lat", "number"), Float).label("lat"),
            cast(_typed(fields, "lon", "number"), Float).label("lon"),
        )
        .where(ProspectSource.account_id == account_id, not_(is_demo_source()))
        .distinct(ProspectSource.lead_id)
        .order_by(ProspectSource.lead_id, ProspectSource.fetched_at.desc(), ProspectSource.id)
        .subquery("latest_source")
    )


def phone_e164() -> ColumnElement:
    """NULL unless the phone normalises (Python `normalize_phone`): +international with 8-15 digits, or a French 0X."""
    cleaned = func.regexp_replace(cast(Lead.phone, String), r"[^0-9+]", "", "g")
    digits = func.regexp_replace(cleaned, r"\D", "", "g")
    international = case(
        (cleaned.like("00%"), func.regexp_replace(func.substr(cleaned, 3), r"\D", "", "g")),
        (cleaned.like("+%"), digits),
    )
    return case(
        (and_(international.is_not(None), func.length(international).between(8, 15)), literal("+") + international),
        (
            and_(international.is_(None), func.length(digits) == 10, digits.like("0%")),
            literal("+33") + func.substr(digits, 2),
        ),
    )


def _email() -> ColumnElement:
    return func.lower(func.btrim(cast(Lead.email, String)))


def email_ok() -> ColumnElement[bool]:
    email = _email()
    return and_(
        heat_sql.known(Lead.email) == 1,
        email.op("~")(EMAIL_RE),
        not_(func.split_part(email, "@", 2).op("~")(PLACEHOLDER_RE)),
    )


def _website_domain() -> ColumnElement:
    """The host of the website (the Python `normalize.normalize_domain`): scheme, www., path and port dropped."""
    bare = func.regexp_replace(func.lower(func.btrim(cast(Lead.website, String))), r"^([a-z][a-z0-9+.-]*:)?//", "")
    host = func.substring(bare, r"^([^/?#:]+)")
    return func.regexp_replace(host, r"^www\.", "")


def _digest(kind: str, value: ColumnElement) -> ColumnElement:
    return func.encode(func.sha256(func.convert_to(literal(f"{kind}:") + value, "UTF8")), "hex")


def suppressed() -> ColumnElement[bool]:
    """On the organisation's do-not-contact list by e-mail, phone or website domain (digests, never clear text)."""

    def listed(kind: str, value: ColumnElement) -> ColumnElement[bool]:
        return and_(
            value.is_not(None),
            exists(
                select(1).where(
                    SuppressionEntry.account_id == Lead.account_id,
                    SuppressionEntry.kind == kind,
                    SuppressionEntry.identity_hash == _digest(kind, value),
                )
            ),
        )

    return or_(listed("email", _email()), listed("phone", phone_e164()), listed("domain", _website_domain()))


def opted_out() -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(Contact)
        .join(ConsentCurrent, ConsentCurrent.contact_id == Contact.id)
        .where(
            Contact.account_id == Lead.account_id,
            Contact.lead_id == Lead.id,
            ConsentCurrent.channel == "email",
            ConsentCurrent.status == "opted_out",
        )
    )


def confirmed_demo() -> ColumnElement[bool]:
    """A demo source on the prospect, or a consent record seeded as demo data (names alone are never proof)."""
    source = exists(
        select(1).where(
            ProspectSource.account_id == Lead.account_id, ProspectSource.lead_id == Lead.id, is_demo_source()
        )
    )
    seed = exists(
        select(1)
        .select_from(Contact)
        .join(ConsentRecord, ConsentRecord.contact_id == Contact.id)
        .where(
            Contact.account_id == Lead.account_id,
            Contact.lead_id == Lead.id,
            ConsentRecord.account_id == Lead.account_id,
            ConsentRecord.source == "demo_seed",
        )
    )
    return or_(source, seed)


def _strict(expression: ColumnElement[bool]) -> ColumnElement[bool]:
    """TRUE or FALSE, never NULL: a missing value (no position, no e-mail…) must read as "no", so that its negation
    is "yes" and the prospect lands in the queue instead of vanishing from both lists."""
    return func.coalesce(expression, false())


def excluded() -> ColumnElement[bool]:
    return _strict(
        or_(func.coalesce(Lead.review_status, "") == "rejected", suppressed(), opted_out(), confirmed_demo())
    )


def qualified(src: Subquery, now: Optional[datetime] = None) -> ColumnElement[bool]:
    """Qualified priority: the Python `eligibility.evaluate(...)["eligible"]`. `src` is `latest_source(account_id)`."""
    now = _now(now)
    rule = policy.rules()
    address = func.btrim(src.c.address)
    return _strict(
        and_(
            heat_sql.known(Lead.full_name) == 1,
            email_ok(),
            phone_e164().is_not(None),
            src.c.source_id.is_not(None),
            src.c.fetched_at >= now - timedelta(days=rule.source_days),
            heat_sql.known(src.c.address) == 1,
            func.length(address) >= policy.MIN_ADDRESS_CHARS,
            src.c.lat.between(-90, 90),
            src.c.lon.between(-180, 180),
            not_(and_(src.c.lat == 0, src.c.lon == 0)),
            Lead.fit_score.is_not(None),
            Lead.fit_score >= rule.min_fit,
            Lead.qualification_scored_at >= now - timedelta(days=rule.fit_days),
            not_(excluded()),
        )
    )


def hot(src: Subquery, now: Optional[datetime] = None) -> ColumnElement[bool]:
    """Qualified AND a recent, detected, evidenced `commercial_intent` signal that points at a real source of it."""
    now = _now(now)
    intent = exists(
        select(1)
        .select_from(ProspectSignal)
        .join(ProspectSource, ProspectSource.id == ProspectSignal.source_id)
        .where(
            ProspectSignal.account_id == Lead.account_id,
            ProspectSignal.lead_id == Lead.id,
            ProspectSignal.signal_key == policy.INTENT_SIGNAL,
            ProspectSignal.state == "detected",
            func.length(func.btrim(ProspectSignal.evidence)) > 0,
            ProspectSignal.created_at >= now - timedelta(days=policy.rules().intent_days),
            ProspectSource.account_id == Lead.account_id,
            ProspectSource.lead_id == Lead.id,
            not_(is_demo_source()),
        )
    )
    return _strict(and_(qualified(src, now), intent))
