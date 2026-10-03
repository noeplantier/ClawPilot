"""Discovery pipeline: source → normalise → deduplicate → signals → score, all in dry-run (nothing is sent).

This is the only module of the package that talks to the database, and only through repositories.
The caller owns the transaction (the FastAPI session dependency commits on success).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from repositories import audit_repo, prospect_repo, suppression_repo, usage_repo
from services.outreach_os import contact
from services.outreach_os import signals as sig
from services.outreach_os.dedupe import build_candidate, dedupe
from services.outreach_os.scoring import ScoreConfig, compute_score
from services.outreach_os.sources import SiteFetcher, SourceAdapter
from services.outreach_os.types import Candidate, RawListing

if TYPE_CHECKING:
    from db.models import ScoreVersion

VERTICAL = "restaurant"


@dataclass
class DiscoverySummary:
    listings_found: int = 0
    entities: int = 0
    duplicates_merged: int = 0
    suppressed: int = 0
    prospects_created: int = 0
    prospects_updated: int = 0
    sources_recorded: int = 0
    sites_checked: int = 0
    signals_recorded: int = 0
    scores_recorded: int = 0


async def run_discovery(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    adapter: SourceAdapter,
    fetcher: SiteFetcher,
    now: date,
    user_id: Optional[uuid.UUID] = None,
    vertical: str = VERTICAL,
    country: str = "FR",
    language: str = "fr",
    trust_absence: bool = True,
) -> DiscoverySummary:
    summary = DiscoverySummary()
    listings = adapter.fetch()
    summary.listings_found = len(listings)
    candidates = dedupe([build_candidate(listing) for listing in listings])
    summary.entities = len(candidates)
    summary.duplicates_merged = summary.listings_found - summary.entities

    version = await prospect_repo.active_score_version(session, account_id)
    if version is None:
        version = await prospect_repo.create_score_version(session, account_id, ScoreConfig(), user_id)
    config = prospect_repo.config_of(version)

    for cand in candidates:
        if await suppression_repo.is_suppressed(
            session, account_id, email=cand.email, phone=cand.phone, domain=cand.domain
        ):
            summary.suppressed += 1
            continue
        await _ingest(
            session,
            account_id,
            cand,
            adapter,
            fetcher,
            version,
            config,
            now,
            vertical,
            summary,
            user_id,
            country=country,
            language=language,
            trust_absence=trust_absence,
        )

    await usage_repo.record(session, account_id, "discovery_run", 1, {"source": adapter.name})
    await usage_repo.record(session, account_id, "signals_analyzed", summary.entities - summary.suppressed)
    await audit_repo.log(
        session,
        account_id,
        action="discovery.run",
        resource_type="discovery",
        actor_type="user" if user_id else "system",
        actor_user_id=user_id,
        diff={"source": adapter.name, "dry_run": True, **summary.__dict__},
    )
    return summary


@dataclass
class ImportPreview:
    entities: int = 0
    duplicates_merged: int = 0
    suppressed: int = 0
    would_create: int = 0
    would_update: int = 0


async def preview_listings(session: AsyncSession, account_id: uuid.UUID, listings: list[RawListing]) -> ImportPreview:
    """What importing these listings would do, without writing anything (read-only)."""
    candidates = dedupe([build_candidate(listing) for listing in listings])
    out = ImportPreview(entities=len(candidates), duplicates_merged=len(listings) - len(candidates))
    for cand in candidates:
        if await suppression_repo.is_suppressed(
            session, account_id, email=cand.email, phone=cand.phone, domain=cand.domain
        ):
            out.suppressed += 1
        elif await prospect_repo.find_by_keys(session, account_id, cand.match_keys) is None:
            out.would_create += 1
        else:
            out.would_update += 1
    return out


async def _ingest(
    session: AsyncSession,
    account_id: uuid.UUID,
    cand: Candidate,
    adapter: SourceAdapter,
    fetcher: SiteFetcher,
    version: ScoreVersion,
    config: ScoreConfig,
    now: date,
    vertical: str,
    summary: DiscoverySummary,
    user_id: Optional[uuid.UUID],
    *,
    country: str = "FR",
    language: str = "fr",
    trust_absence: bool = True,
) -> None:
    lead = await prospect_repo.find_by_keys(session, account_id, cand.match_keys)
    if lead is None:
        lead = await prospect_repo.create_from_candidate(
            session, account_id, cand, vertical=vertical, source_name=adapter.name, country=country, language=language
        )
        summary.prospects_created += 1
        await audit_repo.log(
            session,
            account_id,
            action="prospect.created",
            resource_type="prospect",
            resource_id=lead.id,
            actor_type="user" if user_id else "system",
            actor_user_id=user_id,
            diff={"source": adapter.name},
        )
    else:
        await prospect_repo.merge_keys(session, lead, cand.match_keys)
        summary.prospects_updated += 1

    source_ids = []
    for listing in cand.all_listings:
        source, created = await prospect_repo.add_source(session, account_id, lead.id, listing, adapter.license_note)
        source_ids.append(source.id)
        summary.sources_recorded += int(created)

    # The fetcher may block on the network: keep the event loop free.
    snapshot = (
        await asyncio.to_thread(fetcher.fetch, cand.listing.website) if cand.domain and cand.listing.website else None
    )
    if snapshot is not None:
        summary.sites_checked += 1
        found = contact.extract_contact_email(snapshot.html, cand.listing.website) if not lead.email else None
        if found and await prospect_repo.fill_email(session, account_id, lead, found):
            await audit_repo.log(
                session,
                account_id,
                action="prospect.email_found",
                resource_type="prospect",
                resource_id=lead.id,
                actor_type="user" if user_id else "system",
                actor_user_id=user_id,
                diff={"origin": "mailto link on the business's own homepage", "site": cand.domain},
            )
    results = sig.analyze(cand.listing, snapshot, now=now, stale_days=config.stale_days, trust_absence=trust_absence)
    summary.signals_recorded += await prospect_repo.append_signals(session, account_id, lead.id, results, source_ids[0])
    if await prospect_repo.append_score(session, account_id, lead.id, version, compute_score(results, config)):
        summary.scores_recorded += 1


async def rescore_all(session: AsyncSession, account_id: uuid.UUID, version: ScoreVersion, config: ScoreConfig) -> int:
    """Recompute scores from the stored signals with `config` (no re-fetching). Returns rows appended."""
    from services.outreach_os.types import SignalResult, SignalState

    appended = 0
    leads, _ = await prospect_repo.list_prospects(session, account_id, limit=10_000)
    for lead, _score, _coverage in leads:
        stored = await prospect_repo.current_signals(session, lead.id)
        results = [SignalResult(s.signal_key, SignalState(s.state), s.evidence) for s in stored]
        if await prospect_repo.append_score(session, account_id, lead.id, version, compute_score(results, config)):
            appended += 1
    return appended
