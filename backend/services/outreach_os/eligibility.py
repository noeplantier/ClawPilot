"""One eligibility policy for every commercial prospect surface (map, lists, counters, dashboard, suggestions).

Pure: no I/O, `now` injected. The SQL twin is `repositories/eligibility_sql.py`; both are tested against each other.

A prospect is **qualified** (shown on the commercial map) when all of this is true, from persisted evidence only:
- a real establishment identity (a name that is not blank / "unknown");
- an e-mail with valid syntax and a phone that normalises (E.164), both published by the source: a valid syntax does not
  prove the mailbox exists, and a phone does not prove WhatsApp;
- a physical address and coordinates (a valid position, never the null island) on its latest non-demo source;
- that source is identifiable and fresh (`OUTREACH_SOURCE_TTL_DAYS`, 30 by default);
- a recent explainable fit score at or above `OUTREACH_MIN_FIT_SCORE` (60 by default).
The website and WhatsApp are NOT required: a prospect with or without a site is judged on the same terms.

It is **hot** only when it is qualified AND carries a recent `commercial_intent` signal that was detected, has evidence
and points at a real source of that same prospect. Need signals (no website, no booking page…) are not purchase
intent: nothing here ever invents one, so "Hot" can legitimately be empty.

Gaps that enrichment could fill are `missing_fields` (the prospect stays in the "to enrich" queue, never contactable by
default). Suppressed, opted-out, rejected or demo records are `reasons` (excluded, not enrichable).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from services.outreach_os.heat import NOT_KNOWN
from services.outreach_os.normalize import normalize_email, normalize_phone

POLICY_VERSION = "map-v2"
DEMO_SOURCE_NAMES = ("fixture_directory", "world_fixture")
INTENT_SIGNAL = "commercial_intent"
PLACEHOLDER_EMAIL_DOMAIN = re.compile(
    r"(^|\.)(example|invalid|test|localhost)(\.|$)"
)  # reserved names: never a real mailbox
MIN_ADDRESS_CHARS = 5

# Machine-readable gaps, in the order the UI lists them.
MISSING_FIELDS = (
    "name_missing",
    "email_missing",
    "email_invalid",
    "phone_missing",
    "phone_invalid",
    "address_missing",
    "coordinates_missing",
    "source_missing",
    "source_stale",
    "fit_missing",
    "fit_stale",
    "fit_low",
)
EXCLUSIONS = ("rejected", "suppressed", "opted_out", "demo_data")


@dataclass(frozen=True)
class Rules:
    source_days: int
    fit_days: int
    intent_days: int
    min_fit: int


def _days(name: str, default: int) -> int:
    try:
        return max(1, min(365, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def rules() -> Rules:
    try:
        min_fit = max(0, min(100, int(os.environ.get("OUTREACH_MIN_FIT_SCORE", 60))))
    except (TypeError, ValueError):
        min_fit = 60
    return Rules(
        source_days=_days("OUTREACH_SOURCE_TTL_DAYS", 30),
        fit_days=_days("OUTREACH_FIT_TTL_DAYS", 30),
        intent_days=_days("OUTREACH_INTENT_TTL_DAYS", 30),
        min_fit=min_fit,
    )


def is_known(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() not in NOT_KNOWN


def email_state(raw: object) -> Optional[str]:
    """None when usable, else the gap: `email_missing` (blank) or `email_invalid` (syntax / placeholder domain)."""
    if not is_known(raw):
        return "email_missing"
    email = normalize_email(str(raw))
    if email is None or PLACEHOLDER_EMAIL_DOMAIN.search(email.rsplit("@", 1)[-1]):
        return "email_invalid"
    return None


def phone_state(raw: object) -> Optional[str]:
    if not is_known(raw):
        return "phone_missing"
    return None if normalize_phone(str(raw)) else "phone_invalid"


def address_ok(value: object) -> bool:
    return is_known(value) and len(str(value).strip()) >= MIN_ADDRESS_CHARS


def coordinates_ok(lat: object, lon: object) -> bool:
    """A real position: numbers (a bool is not one), in range, and not the null island an empty value turns into."""
    if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)):
        return False
    if not isinstance(lon, (int, float)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    return not (lat == 0 and lon == 0)


def is_demo_source(source: Mapping[str, Any]) -> bool:
    """Durable demo provenance only; a name that merely looks fictional is never proof."""
    fields = source.get("fields")
    return bool(
        source.get("source_name") in DEMO_SOURCE_NAMES
        or str(source.get("source_url") or "").startswith("fixture://")
        or "fictional data" in str(source.get("license_note") or "").lower()
        or (isinstance(fields, dict) and fields.get("demo_data") is True)
    )


def _aware(value: object) -> Optional[datetime]:
    return value if isinstance(value, datetime) and value.tzinfo is not None else None


def latest_source(sources: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    real = [s for s in sources if not is_demo_source(s) and _aware(s.get("fetched_at"))]
    return max(real, key=lambda s: s["fetched_at"]) if real else None


def evaluate(
    lead: Mapping[str, Any],
    *,
    sources: Sequence[Mapping[str, Any]],
    signals: Sequence[Mapping[str, Any]] = (),
    suppressed: bool = False,
    opted_out: bool = False,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Explain one prospect's status from persisted evidence. An unknown is never read as a value, never invented."""
    now = now or datetime.now(timezone.utc)
    rule = rules()
    missing: list[str] = []

    if not is_known(lead.get("full_name")):
        missing.append("name_missing")
    for gap in (email_state(lead.get("email")), phone_state(lead.get("phone"))):
        if gap:
            missing.append(gap)

    real = [s for s in sources if not is_demo_source(s)]
    source = latest_source(sources)
    fields = (source or {}).get("fields")
    fields = fields if isinstance(fields, dict) else {}
    if not address_ok(fields.get("address")):
        missing.append("address_missing")
    if not coordinates_ok(fields.get("lat"), fields.get("lon")):
        missing.append("coordinates_missing")
    if source is None:
        missing.append("source_missing")
    elif source["fetched_at"] < now - timedelta(days=rule.source_days):
        missing.append("source_stale")

    fit, scored_at = lead.get("fit_score"), _aware(lead.get("qualification_scored_at"))
    if not isinstance(fit, int) or isinstance(fit, bool) or scored_at is None:
        missing.append("fit_missing")
    elif scored_at < now - timedelta(days=rule.fit_days):
        missing.append("fit_stale")
    elif fit < rule.min_fit:
        missing.append("fit_low")

    excluded: list[str] = []
    if lead.get("review_status") == "rejected":
        excluded.append("rejected")
    if suppressed:
        excluded.append("suppressed")
    if opted_out:
        excluded.append("opted_out")
    if any(is_demo_source(s) for s in sources):
        excluded.append("demo_data")

    qualified = not missing and not excluded
    real_ids = {s.get("id") for s in real if s.get("id") is not None}
    intent = qualified and any(
        sig.get("signal_key") == INTENT_SIGNAL
        and sig.get("state") == "detected"
        and bool(str(sig.get("evidence") or "").strip())
        and sig.get("source_id") in real_ids
        and (created := _aware(sig.get("created_at"))) is not None
        and created >= now - timedelta(days=rule.intent_days)
        for sig in signals
    )
    return {
        "eligible": qualified,
        "status": "excluded" if excluded else "qualified" if qualified else "to_enrich",
        "priority": "hot" if intent else "qualified" if qualified else None,
        "priority_label": "Hot — intention observée" if intent else "Qualifié prioritaire" if qualified else None,
        "is_hot": intent,
        "reasons": excluded,
        "missing_fields": missing,
        "policy_version": POLICY_VERSION,
        "evaluated_at": now.isoformat(),
    }
