"""One fail-closed eligibility policy for commercial prospect surfaces.

Digital-need scores are not purchase intent. A prospect is strictly qualified only when
source, freshness, public email, explicit WhatsApp evidence, an official checked website,
and a recent ICP score are all present. Missing evidence stays unknown.
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
    "facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "twitter.com", "x.com", "youtube.com"
)
FREE_EMAIL_DOMAINS = (
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me",
    "protonmail.com", "aol.com", "live.com", "gmx.com", "yandex.com",
)


def _days(name: str, default: int) -> int:
    try:
        return max(1, min(365, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


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
        source for source in sources
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
    email_sources = [
        s for s in valid_sources
        if str((s.get("fields") or {}).get("website") or "").lower() == str(lead.get("website") or "").lower()
    ]
    email_domain = email.rsplit("@", 1)[-1]
    email_ok = bool(
        "@" in email
        and email_domain.count(".")
        and not email.endswith(".example")
        and email_domain not in FREE_EMAIL_DOMAINS
    )
    verification = (website_check or {}).get("email_verification", {}).get(email) == "syntax_valid"
    email_evidence = email_ok and verification and not suppressed
    if not email_ok or not email_sources or not verification or suppressed:
        missing.append("sourced_verified_unsuppressed_business_email")

    phone = str(lead.get("phone") or "")
    digits = "".join(c for c in phone if c.isdigit())
    whatsapp_urls = (website_check or {}).get("whatsapp_urls") or []
    whatsapp = bool(
        phone.startswith("+")
        and 8 <= len(digits) <= 15
        and any(str(url).lower().startswith(("https://wa.me/", "http://wa.me/")) and digits in str(url) for url in whatsapp_urls)
    )
    if not whatsapp:
        missing.append("published_whatsapp_proof_and_normalized_number")

    website = str(lead.get("website") or "")
    try:
        host = (urlsplit(website if "://" in website else f"https://{website}").hostname or "").lower()
    except ValueError:
        host = ""
    host = host[4:] if host.startswith("www.") else host
    site_source = any(str((s.get("fields") or {}).get("website") or "").lower() == website.lower() for s in valid_sources)
    third_party = any(host == domain or host.endswith(f".{domain}") for domain in THIRD_PARTY_HOSTS)
    http_status = (website_check or {}).get("http_status")
    site_ok = (
        website.startswith(("https://", "http://"))
        and bool(host)
        and not host.endswith(".example")
        and not third_party
        and site_source
        and (website_check or {}).get("status") == "completed"
        and isinstance(http_status, int)
        and 200 <= http_status < 400
        and recent((website_check or {}).get("collected_at"), site_days)
    )
    if not site_ok:
        missing.append("recently_checked_official_website")

    fit_at = lead.get("qualification_scored_at")
    fit_ok = isinstance(lead.get("fit_score"), (int, float)) and lead["fit_score"] >= min_fit and recent(fit_at, fit_days)
    if not fit_ok:
        missing.append("recent_icp_fit_score")
    if suppressed:
        reasons.append("suppressed_or_bounced")

    eligible = bool(email_evidence and whatsapp and site_ok and fit_ok and valid_sources and lead.get("id") and lead.get("account_id"))
    intent = any(
        signal.get("signal_key") == "commercial_intent"
        and signal.get("state") == "detected"
        and bool(str(signal.get("evidence") or "").strip())
        and recent(signal.get("created_at"), _days("OUTREACH_INTENT_TTL_DAYS", 30))
        and any(source.get("id") == signal.get("source_id") for source in valid_sources)
        for signal in signals
    )
    return {
        "eligible": eligible,
        "status": "qualified" if eligible else "to_enrich",
        "is_hot": eligible and intent,
        "reasons": reasons,
        "missing_fields": list(dict.fromkeys(missing)),
        "freshness": {
            "source_days": source_days,
            "website_days": site_days,
            "fit_days": fit_days,
        },
        "policy_version": POLICY_VERSION,
        "evaluated_at": now,
    }


def _fresh(column, days: int, now: datetime) -> ColumnElement[bool]:  # type: ignore[no-untyped-def]
    return column >= now - timedelta(days=days)


def strict_conditions(now: datetime | None = None) -> list[ColumnElement[bool]]:
    """SQL predicate shared by server-side lists, aggregates, map and audience reads."""
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
            ~ProspectSource.license_note.ilike("%fictional data%"),
            _fresh(ProspectSource.fetched_at, source_days, now),
            func.lower(ProspectSource.fields["website"].astext) == func.lower(Lead.website),
        )
    )
    email_syntax = Lead.email.op("~*")(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    no_example_email = ~func.lower(Lead.email).like("%.example")
    business_email = func.split_part(func.lower(func.btrim(Lead.email)), "@", 2).notin_(FREE_EMAIL_DOMAINS)
    normalized_phone = Lead.phone.op("~*")(r"^\+[1-9][0-9]{7,14}$")
    published_email = PublicPageCache.data["emails"].contains(func.jsonb_build_array(Lead.email)) & (
        PublicPageCache.data["email_verification"][func.lower(Lead.email)].astext == "syntax_valid"
    )
    phone_digits = func.regexp_replace(Lead.phone, r"[^0-9]", "", "g")
    published_whatsapp = func.lower(cast(PublicPageCache.data["whatsapp_urls"], String)).like(
        func.concat("%wa.me/", phone_digits, "%")
    )
    official_website = (
        Lead.website.is_not(None)
        & func.lower(Lead.website).like("http%")
        & ~func.lower(Lead.website).like("%.example%")
        & and_(
            *(~func.lower(Lead.website).op("~*")(rf"(^|//)(www\.)?{re.escape(domain)}([/:?#]|$)") for domain in THIRD_PARTY_HOSTS)
        )
    )
    site_check = exists(
        select(1).select_from(PublicPageCache).where(
            PublicPageCache.url == Lead.website,
            PublicPageCache.status == "completed",
            _fresh(PublicPageCache.collected_at, site_days, now),
            cast(PublicPageCache.data["homepage_http_status"].astext, Integer).between(200, 399),
            published_email,
            published_whatsapp,
        )
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
        business_email,
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
