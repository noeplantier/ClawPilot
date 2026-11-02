"""One fail-closed eligibility policy for commercial prospect surfaces.

Digital-need scores are not purchase intent. A prospect is strictly qualified only when
source, freshness, public email, explicit WhatsApp evidence, an official checked website,
and a recent ICP score are all present. Missing evidence stays unknown.
Real businesses using Gmail are never rejected on email provider grounds.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import Integer, String, and_, cast, exists, func, literal, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from db.models import (
    ConsentCurrent,
    ConsentRecord,
    Contact,
    Lead,
    ProspectSignal,
    ProspectSource,
    PublicPageCache,
    SuppressionEntry,
)

POLICY_VERSION = "strict-v1"
DEMO_SOURCE_NAMES = ("fixture_directory", "world_fixture")
THIRD_PARTY_HOSTS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
)


def _days(name: str, default: int) -> int:
    try:
        return max(1, min(365, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def _extract_digits(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def _match_whatsapp(phone_digits: str, whatsapp_urls: list[str]) -> bool:
    if not phone_digits or len(phone_digits) < 8 or len(phone_digits) > 15:
        return False
    # Local French: 0612345678 -> 612345678; International: 33612345678 -> 612345678
    significant = phone_digits
    if len(phone_digits) == 10 and phone_digits.startswith("0"):
        significant = phone_digits[1:]
    elif len(phone_digits) == 11 and phone_digits.startswith("33"):
        significant = phone_digits[2:]

    for raw_url in whatsapp_urls:
        url_str = str(raw_url).lower().strip()
        if not (url_str.startswith("https://wa.me/") or url_str.startswith("http://wa.me/")):
            continue
        url_digits = "".join(c for c in url_str if c.isdigit())
        if phone_digits in url_digits or significant in url_digits:
            return True
    return False


def evaluate(
    lead: dict,
    *,
    sources: list[dict],
    signals: list[dict],
    website_check: dict | None,
    suppressed: bool = False,
    now: datetime | None = None,
) -> dict:
    """Explain one lead's strict status from persisted evidence; no unknown is inferred as a negative."""
    now = now or datetime.now(timezone.utc)
    source_days = _days("OUTREACH_SOURCE_TTL_DAYS", 30)
    site_days = _days("OUTREACH_SITE_TTL_DAYS", 30)
    fit_days = _days("OUTREACH_FIT_TTL_DAYS", 30)
    try:
        min_fit = max(0, min(100, int(os.environ.get("OUTREACH_MIN_FIT_SCORE", 60))))
    except (TypeError, ValueError):
        min_fit = 60

    def recent(value, days: int) -> bool:  # type: ignore[no-untyped-def]
        return isinstance(value, datetime) and value.tzinfo is not None and value >= now - timedelta(days=days)

    reasons: list[str] = []
    missing: list[str] = []

    valid_sources = [
        source
        for source in sources
        if source.get("account_id") == lead.get("account_id")
        and source.get("lead_id") == lead.get("id")
        and source.get("source_name") not in DEMO_SOURCE_NAMES
        and not str(source.get("source_url", "")).startswith("fixture://")
        and "fictional data" not in str(source.get("license_note", "")).lower()
        and not bool((source.get("fields") or {}).get("demo_data"))
        and recent(source.get("fetched_at"), source_days)
    ]
    if not lead.get("id") or not lead.get("account_id"):
        reasons.append("missing_internal_identity")
    if not valid_sources:
        missing.append("fresh_identifiable_source")

    email = str(lead.get("email") or "").strip().lower()
    email_domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    email_syntax_ok = bool(
        "@" in email
        and "." in email_domain
        and not email.endswith(".example")
        and not email_domain.startswith("example.")
        and not email.endswith("@example.com")
    )
    email_verification = (website_check or {}).get("email_verification", {}).get(email)
    verification_ok = email_verification in ("syntax_valid", "deliverable", "mx_valid")
    if not email_syntax_ok or not verification_ok or suppressed:
        missing.append("sourced_verified_unsuppressed_business_email")

    phone = str(lead.get("phone") or "").strip()
    digits = _extract_digits(phone)
    whatsapp_urls = (website_check or {}).get("whatsapp_urls") or []
    has_whatsapp_proof = _match_whatsapp(digits, whatsapp_urls)
    if not (phone and digits and has_whatsapp_proof):
        missing.append("published_whatsapp_proof_and_normalized_number")

    website = str(lead.get("website") or "").strip()
    try:
        host = (urlsplit(website if "://" in website else f"https://{website}").hostname or "").lower()
    except ValueError:
        host = ""
    host = host[4:] if host.startswith("www.") else host
    third_party = any(host == domain or host.endswith(f".{domain}") for domain in THIRD_PARTY_HOSTS)
    http_status = (website_check or {}).get("http_status")
    site_status = (website_check or {}).get("status")
    site_collected = (website_check or {}).get("collected_at")
    recent_site = recent(site_collected, site_days) if site_collected else False

    if not website or third_party or site_status != "completed" or http_status != 200 or not recent_site:
        missing.append("recently_checked_official_website")

    fit_score = lead.get("fit_score")
    scored_at = lead.get("qualification_scored_at")
    recent_score = recent(scored_at, fit_days) if scored_at else False
    if fit_score is None or fit_score < min_fit or not recent_score:
        missing.append("recent_icp_fit_score")

    if suppressed:
        reasons.append("suppressed_or_bounced")

    has_intent = False
    intent_signals = [
        sig
        for sig in signals
        if sig.get("signal_key") == "commercial_intent"
        and sig.get("state") == "detected"
        and bool(str(sig.get("evidence") or "").strip())
        and recent(sig.get("created_at"), _days("OUTREACH_INTENT_TTL_DAYS", 30))
        and any(s.get("id") == sig.get("source_id") for s in valid_sources)
    ]
    if intent_signals:
        has_intent = True

    is_qualified = len(reasons) == 0 and len(missing) == 0

    return {
        "eligible": is_qualified,
        "status": "qualified" if is_qualified else "to_enrich",
        "priority_label": "Hot — intention observée" if (is_qualified and has_intent) else ("Qualifié prioritaire" if is_qualified else "À enrichir"),
        "is_hot": is_qualified and has_intent,
        "reasons": reasons,
        "missing_fields": missing,
        "policy_version": POLICY_VERSION,
        "evaluated_at": now.isoformat(),
    }


def _fresh(column, days: int, now: datetime) -> ColumnElement[bool]:  # type: ignore[no-untyped-def]
    return column >= now - timedelta(days=days)


def strict_conditions(now: datetime | None = None) -> list[ColumnElement[bool]]:
    """Fail-closed conditions: complete provenance required across CRM tables."""
    now = now or datetime.now(timezone.utc)
    source_days = _days("OUTREACH_SOURCE_TTL_DAYS", 30)
    site_days = _days("OUTREACH_SITE_TTL_DAYS", 30)
    fit_days = _days("OUTREACH_FIT_TTL_DAYS", 30)
    try:
        min_fit = max(0, min(100, int(os.environ.get("OUTREACH_MIN_FIT_SCORE", 60))))
    except (TypeError, ValueError):
        min_fit = 60

    source = exists(
        select(1).select_from(ProspectSource).where(
            ProspectSource.account_id == Lead.account_id,
            ProspectSource.lead_id == Lead.id,
            ProspectSource.source_name.notin_(DEMO_SOURCE_NAMES),
            ~ProspectSource.source_url.startswith("fixture://"),
            func.lower(ProspectSource.license_note).notilike("%fictional data%"),
            _fresh(ProspectSource.fetched_at, source_days, now),
        )
    )

    email_syntax = and_(
        func.position("@", Lead.email) > 1,
        func.position(".", func.split_part(Lead.email, "@", 2)) > 1,
    )
    no_example_email = and_(
        ~Lead.email.ilike("%.example"),
        ~Lead.email.ilike("%@example.%"),
    )

    normalized_phone = func.length(func.regexp_replace(Lead.phone, r"\D", "", "g")) >= 8

    official_website = and_(
        Lead.website.is_not(None),
        ~Lead.website.ilike("%.example/%"),
        ~Lead.website.ilike("%.example"),
        *[~Lead.website.ilike(f"%{domain}%") for domain in THIRD_PARTY_HOSTS],
    )

    published_whatsapp = exists(
        select(1)
        .select_from(PublicPageCache)
        .where(
            PublicPageCache.url == Lead.website,
            PublicPageCache.status == "completed",
            _fresh(PublicPageCache.collected_at, site_days, now),
            cast(PublicPageCache.data["whatsapp_urls"].astext, String).ilike(
                func.concat("%", func.regexp_replace(Lead.phone, r"\D", "", "g"), "%")
            ),
        )
    )

    site_check = and_(
        exists(
            select(1).select_from(PublicPageCache).where(
                PublicPageCache.url == Lead.website,
                PublicPageCache.status == "completed",
                cast(PublicPageCache.data["http_status"].astext, Integer) == 200,
                _fresh(PublicPageCache.collected_at, site_days, now),
            )
        ),
        published_whatsapp,
    )

    no_suppression = not_(
        exists(
            select(1).select_from(SuppressionEntry).where(
                SuppressionEntry.account_id == Lead.account_id,
                SuppressionEntry.kind == "email",
                SuppressionEntry.identity_hash
                == func.encode(
                    func.sha256(func.convert_to(literal("email:") + func.lower(func.btrim(Lead.email)), "UTF8")),
                    "hex",
                ),
            )
        )
    )

    no_domain_suppression = not_(
        exists(
            select(1).select_from(SuppressionEntry).where(
                SuppressionEntry.account_id == Lead.account_id,
                SuppressionEntry.kind == "domain",
                SuppressionEntry.identity_hash
                == func.encode(
                    func.sha256(
                        func.convert_to(
                            literal("domain:") + func.split_part(func.lower(func.btrim(Lead.email)), "@", 2),
                            "UTF8",
                        )
                    ),
                    "hex",
                ),
            )
        )
    )

    no_phone_suppression = not_(
        exists(
            select(1).select_from(SuppressionEntry).where(
                SuppressionEntry.account_id == Lead.account_id,
                SuppressionEntry.kind == "phone",
                SuppressionEntry.identity_hash
                == func.encode(
                    func.sha256(func.convert_to(literal("phone:") + Lead.phone, "UTF8")),
                    "hex",
                ),
            )
        )
    )

    not_opted_out = not_(
        exists(
            select(1)
            .select_from(Contact)
            .join(ConsentCurrent, ConsentCurrent.contact_id == Contact.id)
            .where(
                Contact.account_id == Lead.account_id,
                Contact.lead_id == Lead.id,
                func.lower(Contact.email) == func.lower(Lead.email),
                ConsentCurrent.channel == "email",
                ConsentCurrent.status == "opted_out",
            )
        )
    )

    qualified = and_(
        Lead.email.is_not(None),
        email_syntax,
        no_example_email,
        Lead.phone.is_not(None),
        normalized_phone,
        source,
        official_website,
        site_check,
        Lead.fit_score.is_not(None),
        Lead.fit_score >= min_fit,
        Lead.qualification_scored_at.is_not(None),
        _fresh(Lead.qualification_scored_at, fit_days, now),
        no_suppression,
        no_domain_suppression,
        no_phone_suppression,
        not_opted_out,
    )
    return [qualified]


def strict_expression(now: datetime | None = None) -> ColumnElement[bool]:
    return and_(*strict_conditions(now))


def hot_conditions(now: datetime | None = None) -> list[ColumnElement[bool]]:
    """Strict qualification plus a recent, source-linked, explicit commercial-intent signal."""
    now = now or datetime.now(timezone.utc)
    intent = exists(
        select(1).select_from(ProspectSignal).join(
            ProspectSource, ProspectSource.id == ProspectSignal.source_id
        ).where(
            ProspectSignal.account_id == Lead.account_id,
            ProspectSignal.lead_id == Lead.id,
            ProspectSignal.signal_key == "commercial_intent",
            ProspectSignal.state == "detected",
            func.length(func.btrim(ProspectSignal.evidence)) > 0,
            _fresh(ProspectSignal.created_at, _days("OUTREACH_INTENT_TTL_DAYS", 30), now),
            ProspectSource.account_id == Lead.account_id,
            ProspectSource.lead_id == Lead.id,
            ProspectSource.source_name.notin_(DEMO_SOURCE_NAMES),
            ~ProspectSource.source_url.startswith("fixture://"),
        )
    )
    return [strict_expression(now), intent]


def hot_expression(now: datetime | None = None) -> ColumnElement[bool]:
    return and_(*hot_conditions(now))


def exclude_confirmed_demo() -> ColumnElement[bool]:
    """Hide records with durable demo provenance; names alone are never used as proof."""
    source_demo = exists(
        select(1).select_from(ProspectSource).where(
            ProspectSource.account_id == Lead.account_id,
            ProspectSource.lead_id == Lead.id,
            ProspectSource.source_name.in_(DEMO_SOURCE_NAMES),
        )
    )
    seed_demo = exists(
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
    return not_(or_(source_demo, seed_demo))
