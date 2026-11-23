"""Automatic, bounded zone discovery for an active mandate.

This module turns one mandate into a persisted `ProspectingBatch`: source → extraction → deduplication →
qualification → staged items. It never creates a draft and never sends anything. Network providers are *injected*:
the periodic task supplies the real ones only when FEATURE_EXTERNAL_SOURCES is enabled, tests supply fakes.

A Hot Lead is never inferred from a guess. Every condition below is either a field the source actually published
(with its URL and observation date) or an explicitly recorded observation. A missing field stays "unknown" and
moves the lead to `enriched`/`qualified_strict`, never to `hot`.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.prospecting import Mandate, ProspectingBatch, ProspectingBatchItem
from repositories import audit_repo, prospect_repo, suppression_repo
from services import overpass_svc, registry_svc
from services.outreach_os import signals as sig
from services.outreach_os.dedupe import build_candidate, dedupe
from services.outreach_os.discovery import SourceParams
from services.outreach_os.source_adapters import FrenchRegistryAdapter, OsmAdapter
from services.outreach_os.types import Candidate, SignalState

FRESHNESS_DAYS = 180  # a source older than this is not a current observation
MAX_LISTINGS_PER_RUN = 60  # bounded extraction, even if a provider returns more
MAX_RADIUS_M = 10_000
MAX_PRIOR_ITEMS = 5_000  # bounded dedupe window against previously seen entities
BACKOFF_MINUTES = 15  # a failed provider is not retried again before this delay
OPPORTUNITY_SIGNAL = sig.PUBLIC_CONTACT_PRESENT

_SECTOR_ALIASES = {
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "restauration": "restaurant",
    "cafe": "cafe",
    "cafes": "cafe",
    "hotel": "hotel",
    "hotels": "hotel",
    "hebergement": "hotel",
    "bakery": "bakery",
    "bakeries": "bakery",
    "boulangerie": "bakery",
    "beauty": "beauty",
    "beaute": "beauty",
    "office": "office",
    "offices": "office",
    "bureau": "office",
    "shop": "shop",
    "boutique": "shop",
    "dentist": "dentist",
    "dentiste": "dentist",
}
_PLURAL = {"bakery": "bakeries"}


class MandateNotRunnable(ValueError):
    """The mandate cannot authorise a discovery run (draft, paused, revoked or expired)."""


class DiscoveryAdapter(Protocol):
    name: str
    license_note: str
    verticals: tuple[str, ...]
    max_radius_m: int

    def fetch(self, params: SourceParams): ...


@dataclass(frozen=True)
class Decision:
    stage: str
    reason: str | None
    checks: dict
    signals: list[dict]


def default_adapters() -> list[DiscoveryAdapter]:
    """The providers already used by /api/sources, with their injected HTTP callables."""
    return [
        OsmAdapter(lambda query: overpass_svc.default_fetcher(query)),
        FrenchRegistryAdapter(lambda params: registry_svc.fetch_page(params)),
    ]


def vertical_for(adapter: DiscoveryAdapter, sector: str) -> str | None:
    """Map the mandate's sector to a vertical this adapter actually offers; never guess one it does not."""
    base = _SECTOR_ALIASES.get(sector.strip().lower(), sector.strip().lower())
    supported = set(adapter.verticals)
    for candidate in (base, _PLURAL.get(base, base + "s"), base.rstrip("s")):
        if candidate in supported:
            return candidate
    return None


def centre_and_radius(zone: dict) -> tuple[float, float, int]:
    """Centre and a bounded radius derived from the mandate's own bbox (no geocoding, no expansion)."""
    south, west, north, east = (float(v) for v in zone["bbox"])
    lat, lon = (south + north) / 2, (west + east) / 2
    span = max(north - south, (east - west) * max(0.1, math.cos(math.radians(lat))))
    radius = min(MAX_RADIUS_M, max(1, round(span / 2 * 111_320)))
    return lat, lon, radius


def within_zone(zone: dict, lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    south, west, north, east = (float(v) for v in zone["bbox"])
    return south <= lat <= north and west <= lon <= east


def qualify(
    cand: Candidate,
    zone: dict,
    sector: str,
    *,
    now: date,
    observed_at: date,
    suppressed: bool = False,
    already_seen: bool = False,
) -> Decision:
    """Stage one deduplicated candidate using only what the source published or an observer measured."""
    listing = cand.listing
    checks = {
        "real_establishment": bool(listing.external_id and cand.name_key and listing.source_url),
        # The adapter was queried with `vertical_for(adapter, sector)`: relevance is enforced by the
        # sector-scoped source query, not re-guessed here from the category text.
        "relevant_activity": bool(listing.category) and bool(sector.strip()),
        "verifiable_location": within_zone(zone, listing.lat, listing.lon)
        and bool(listing.address or listing.city),
        "coherent_address": bool(listing.address and (listing.city or listing.postcode)),
        "sourced_email": bool(cand.email),
        "sourced_phone": bool(cand.phone),
        "suppressed": suppressed,
        "duplicate": already_seen,
    }

    # Freshness has an explicit basis: the source's own date, or the date we observed the record.
    reference = listing.last_updated or observed_at
    checks["fresh_provenance"] = (
        reference <= now
        and (now - reference).days <= FRESHNESS_DAYS
        and bool(listing.source_url)
    )
    basis = "source_last_updated" if listing.last_updated else "observed_at"
    checks["freshness_basis"] = basis  # type: ignore[assignment]  # evidence, not a boolean gate

    observed = sig.analyze(listing, None, now=now, stale_days=FRESHNESS_DAYS, trust_absence=False)
    signals = [{"key": r.key, "state": r.state.value, "evidence": r.evidence} for r in observed]
    checks["observable_signal"] = any(
        r.key == OPPORTUNITY_SIGNAL and r.state == SignalState.DETECTED for r in observed
    )

    if suppressed or already_seen:
        reason = "suppressed" if suppressed else "duplicate"
        return Decision("excluded", reason, checks, signals)

    if not checks["real_establishment"] or not checks["verifiable_location"]:
        reason = "no_identifiable_establishment" if not checks["real_establishment"] else "unverifiable_location"
        return Decision("excluded", reason, checks, signals)

    missing = [
        key
        for key in (
            "relevant_activity",
            "coherent_address",
            "fresh_provenance",
            "sourced_email",
            "sourced_phone",
            "observable_signal",
        )
        if not checks[key]
    ]
    if not missing:
        return Decision("hot", None, checks, signals)
    if set(missing) <= {"sourced_email", "sourced_phone", "observable_signal"}:
        return Decision("qualified_strict", ",".join(missing), checks, signals)
    return Decision("enriched", ",".join(missing), checks, signals)


def _cadence_key(mandate: Mandate, now: datetime) -> str:
    bucket = int(now.timestamp() // (mandate.cadence_minutes * 60))
    return f"mandate:{mandate.id}:{bucket}"


def _config_matches(column, mandate_id: uuid.UUID):
    # ->> returns plain text; a JSONB->text cast would keep the JSON quotes.
    return column["mandate_id"].astext == str(mandate_id)


async def _prior_identity_keys(session: AsyncSession, account_id: uuid.UUID) -> tuple[set[str], set[str]]:
    rows = (
        await session.execute(
            select(ProspectingBatchItem.source_key, ProspectingBatchItem.data)
            .where(ProspectingBatchItem.account_id == account_id)
            .order_by(ProspectingBatchItem.created_at.desc())
            .limit(MAX_PRIOR_ITEMS)
        )
    ).all()
    source_keys: set[str] = set()
    match_keys: set[str] = set()
    for source_key, data in rows:
        source_keys.add(source_key)
        match_keys.update((data or {}).get("match_keys") or [])
    return source_keys, match_keys


async def _hot_count(session: AsyncSession, account_id: uuid.UUID, mandate_id: uuid.UUID, since: datetime | None):
    statement = (
        select(func.count(ProspectingBatchItem.id))
        .join(ProspectingBatch, ProspectingBatchItem.batch_id == ProspectingBatch.id)
        .where(
            ProspectingBatch.account_id == account_id,
            _config_matches(ProspectingBatch.config, mandate_id),
            ProspectingBatchItem.stage == "hot",
        )
    )
    if since is not None:
        statement = statement.where(ProspectingBatchItem.created_at >= since)
    return int((await session.scalar(statement)) or 0)


async def run_mandate_discovery(
    session: AsyncSession,
    mandate: Mandate,
    *,
    adapters: Sequence[DiscoveryAdapter],
    now: datetime | None = None,
    max_listings: int = MAX_LISTINGS_PER_RUN,
) -> dict:
    """Run one bounded discovery window. Idempotent per cadence bucket; caller owns the commit."""
    now = now or datetime.now(timezone.utc)
    if mandate.status != "active":
        raise MandateNotRunnable(f"mandate is {mandate.status}")
    if mandate.expires_at <= now:
        raise MandateNotRunnable("mandate has expired")

    key = _cadence_key(mandate, now)
    existing = await session.scalar(
        select(ProspectingBatch).where(
            ProspectingBatch.account_id == mandate.account_id,
            ProspectingBatch.idempotency_key == key,
        )
    )
    if existing is not None and existing.status in ("completed", "partial"):
        return {**(existing.counters or {}), "batch_id": str(existing.id), "reused": True}

    batch = existing
    if batch is None:
        batch = ProspectingBatch(
            account_id=mandate.account_id,
            created_by_user_id=mandate.created_by_user_id,
            name=f"Mandat {mandate.sector} — {now.date().isoformat()}",
            status="discovering",
            idempotency_key=key,
            config={"mandate_id": str(mandate.id), "zone": mandate.zone, "sector": mandate.sector},
            counters={},
            exclusion_reasons={},
            checkpoint={"adapters_done": [], "adapters_failed": [], "fetched_at": {}},
        )
        session.add(batch)
        await session.flush()
    checkpoint = dict(batch.checkpoint or {})
    done = set(checkpoint.get("adapters_done") or [])
    failed_at = checkpoint.get("last_failed_at") or {}

    lat, lon, radius = centre_and_radius(mandate.zone)
    listings: list = []
    errors: dict[str, str] = {}
    license_by_source: dict[str, str] = {}
    vertical_by_source: dict[str, str] = {}
    primary_vertical: str | None = None
    done_items = set(checkpoint.get("items_done") or [])
    for adapter in adapters:
        if adapter.name in done:
            continue  # resume: never re-issue a call already recorded in the checkpoint
        vertical = vertical_for(adapter, mandate.sector)
        if vertical is None:
            done.add(adapter.name)
            errors[adapter.name] = f"unsupported sector: {mandate.sector}"
            continue
        last_failure = datetime.fromisoformat(failed_at[adapter.name]) if adapter.name in failed_at else None
        if last_failure and now - last_failure < timedelta(minutes=BACKOFF_MINUTES):
            errors[adapter.name] = "backoff: previous provider failure not yet expired"
            continue
        try:
            result = adapter.fetch(
                SourceParams(vertical=vertical, lat=lat, lon=lon, radius_m=min(radius, adapter.max_radius_m),
                             limit=max_listings, country="FR")
            )
        except Exception as exc:  # provider unavailable: record it, never invent results
            errors[adapter.name] = type(exc).__name__
            failed_at[adapter.name] = now.isoformat()
            checkpoint.setdefault("adapters_failed", []).append(adapter.name)
            continue
        listings.extend(result.listings[:max_listings])
        license_by_source[adapter.name] = adapter.license_note
        vertical_by_source[adapter.name] = vertical
        primary_vertical = primary_vertical or vertical
        done.add(adapter.name)
        checkpoint.setdefault("fetched_at", {})[adapter.name] = now.isoformat()
        if len(listings) >= max_listings:
            break

    checkpoint["adapters_done"] = sorted(done)
    checkpoint["last_failed_at"] = failed_at
    candidates = dedupe([build_candidate(listing) for listing in listings[:max_listings]])

    prior_sources, prior_matches = await _prior_identity_keys(session, mandate.account_id)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_used = await _hot_count(session, mandate.account_id, mandate.id, None)
    day_used = await _hot_count(session, mandate.account_id, mandate.id, start_of_day)
    total_left = max(0, mandate.total_volume - total_used)
    day_left = max(0, mandate.daily_volume - day_used)

    previous = batch.counters or {}
    counters = {
        "listings_found": int(previous.get("listings_found", 0)) + len(listings),
        "entities": int(previous.get("entities", 0)) + len(candidates),
        "duplicates_merged": int(previous.get("duplicates_merged", 0)) + max(0, len(listings) - len(candidates)),
        "discovered": int(previous.get("discovered", 0)),
        "enriched": int(previous.get("enriched", 0)),
        "qualified_strict": int(previous.get("qualified_strict", 0)),
        "hot": int(previous.get("hot", 0)),
        "excluded": int(previous.get("excluded", 0)),
        "failed": int(previous.get("failed", 0)) + len(errors),
    }
    reasons: dict[str, int] = dict(batch.exclusion_reasons or {})
    seen_sources = set(prior_sources)
    seen_matches = set(prior_matches)

    for cand in candidates:
        source_key = f"{cand.listing.source_name}:{cand.listing.external_id}"
        if source_key in done_items:
            continue  # resumed batch: this entity was already staged before the interruption
        duplicate = source_key in seen_sources or any(k in seen_matches for k in cand.match_keys)
        suppressed = await suppression_repo.is_suppressed(
            session, mandate.account_id, email=cand.email, phone=cand.phone,
            domain=cand.domain,
        )
        decision = qualify(
            cand, mandate.zone, mandate.sector,
            now=now.date(), observed_at=now.date(), suppressed=suppressed, already_seen=duplicate,
        )
        if decision.stage == "hot" and (total_left <= 0 or day_left <= 0):
            decision = Decision("qualified_strict", "quota_reached", decision.checks, decision.signals)
        seen_sources.add(source_key)
        seen_matches.update(cand.match_keys)
        counters[decision.stage] = counters.get(decision.stage, 0) + 1
        if decision.reason:
            reasons[decision.reason] = reasons.get(decision.reason, 0) + 1
        if decision.stage == "hot":
            total_left -= 1
            day_left -= 1
        lead = None
        if decision.stage != "excluded":
            # A staged lead is a real CRM object with its source recorded, not a fabricated placeholder.
            lead = await prospect_repo.find_by_keys(session, mandate.account_id, cand.match_keys)
            if lead is None:
                lead = await prospect_repo.create_from_candidate(
                    session, mandate.account_id, cand,
                    vertical=vertical_by_source.get(
                        cand.listing.source_name, primary_vertical or mandate.sector.strip().lower()
                    ),
                    source_name=cand.listing.source_name,
                )
            else:
                await prospect_repo.merge_keys(session, lead, cand.match_keys)
            await prospect_repo.add_source(
                session, mandate.account_id, lead.id, cand.listing,
                license_by_source.get(cand.listing.source_name, "licence not stated by source"),
            )
        done_items.add(source_key)
        session.add(
            ProspectingBatchItem(
                batch_id=batch.id,
                account_id=mandate.account_id,
                lead_id=lead.id if lead is not None else None,
                source_key=source_key,
                name=cand.listing.name[:300],
                category=(cand.listing.category or "")[:80],
                stage=decision.stage,
                exclusion_reason=decision.reason[:120] if decision.reason else None,
                data={
                    "source_name": cand.listing.source_name,
                    "source_url": cand.listing.source_url,
                    "external_id": cand.listing.external_id,
                    "address": cand.listing.address,
                    "postcode": cand.listing.postcode,
                    "city": cand.listing.city,
                    "lat": cand.listing.lat,
                    "lon": cand.listing.lon,
                    "email": cand.email,
                    "phone": cand.phone,
                    "website": cand.listing.website,
                    "source_last_updated": cand.listing.last_updated.isoformat() if cand.listing.last_updated else None,
                    "observed_at": now.date().isoformat(),
                    "match_keys": cand.match_keys,
                    "merged_from": [
                        {"source_name": o.source_name, "source_url": o.source_url, "external_id": o.external_id}
                        for o in cand.merged_from
                    ],
                    "checks": decision.checks,
                    "signals": decision.signals,
                },
            )
        )

    checkpoint["items_done"] = sorted(done_items)
    batch.counters = counters
    batch.exclusion_reasons = reasons
    batch.checkpoint = checkpoint
    batch.error_summary = "; ".join(f"{k}: {v}" for k, v in errors.items()) or None
    batch.status = "failed" if errors and not listings else ("partial" if errors else "completed")
    batch.started_at = batch.started_at or now
    batch.completed_at = now if batch.status in ("completed", "partial", "failed") else None
    await audit_repo.log(
        session,
        mandate.account_id,
        action="mandate.discovery",
        resource_type="mandate",
        resource_id=mandate.id,
        actor_type="system",
        diff={"dry_run": True, "idempotency_key": key, **counters},
    )
    return {**counters, "batch_id": str(batch.id), "reused": False}


def is_due(last_run_at: datetime | None, cadence_minutes: int, now: datetime) -> bool:
    """A cadence is a minimum interval, not a promise to run exactly on it."""
    if last_run_at is None:
        return True
    return now - last_run_at >= timedelta(minutes=cadence_minutes)
