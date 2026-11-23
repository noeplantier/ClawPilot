"""Automatic discovery: bounded zone, real sources, staged qualification, idempotence.

Everything here is offline: the HTTP callables are never real and no database, SMTP, AI or provider is touched.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from db.models.prospecting import Mandate
from services import discovery_engine as engine
from services.outreach_os.dedupe import build_candidate, dedupe
from services.outreach_os.types import RawListing

ZONE = {"label": "Lyon 2e", "bbox": [45.75, 4.82, 45.77, 4.84]}
NOW = date(2026, 11, 23)


def listing(**over):
    base = dict(
        external_id="registry/123456789",
        name="Le Bouchon",
        source_name="registry_fr",
        source_url="https://annuaire-entreprises.data.gouv.fr/entreprise/123456789",
        category="56.10A",
        address="12 rue de la République",
        postcode="69002",
        city="Lyon",
        phone="+33612345678",
        email="bonjour@lebouchon.fr",
        website="https://lebouchon.fr",
        last_updated=date(2026, 11, 20),
        lat=45.76,
        lon=4.83,
    )
    return RawListing(**{**base, **over})


def qualified(cand, **over):
    opts = dict(now=NOW, observed_at=NOW)
    opts.update(over)
    return engine.qualify(cand, ZONE, "restaurants", **opts)


def test_zone_centre_and_radius_stay_inside_the_mandate_bbox():
    lat, lon, radius = engine.centre_and_radius(ZONE)
    assert 45.75 < lat < 45.77 and 4.82 < lon < 4.84
    assert 0 < radius <= engine.MAX_RADIUS_M
    assert engine.within_zone(ZONE, lat, lon)
    assert not engine.within_zone(ZONE, 48.0, 2.0)
    assert not engine.within_zone(ZONE, None, None)


def test_sector_is_mapped_only_to_verticals_the_adapter_offers():
    class Adapter:
        verticals = ("restaurant", "cafe", "hotel")

    assert engine.vertical_for(Adapter(), "restaurants") == "restaurant"
    assert engine.vertical_for(Adapter(), "Boulangerie") is None
    assert engine.vertical_for(Adapter(), "dentiste") is None


def test_a_complete_observation_becomes_a_hot_lead_with_visible_provenance():
    cand = build_candidate(listing())
    decision = qualified(cand)
    assert decision.stage == "hot" and decision.reason is None
    assert decision.checks["sourced_email"] and decision.checks["sourced_phone"]
    assert decision.checks["fresh_provenance"] and decision.checks["observable_signal"]
    assert decision.checks["freshness_basis"] == "source_last_updated"
    assert any(s["key"] == engine.OPPORTUNITY_SIGNAL and s["state"] == "detected" for s in decision.signals)


def test_missing_contact_is_qualified_strict_and_missing_address_stays_to_enrich():
    assert qualified(build_candidate(listing(phone=None))).stage == "qualified_strict"
    assert "sourced_phone" in qualified(build_candidate(listing(phone=None))).reason
    incomplete = qualified(build_candidate(listing(address=None, postcode=None)))
    assert incomplete.stage == "enriched" and not incomplete.checks["coherent_address"]


def test_unknown_absence_is_never_reported_as_a_website_problem():
    decision = qualified(build_candidate(listing(website=None)))
    no_website = next(s for s in decision.signals if s["key"] == "no_website")
    assert no_website["state"] == "unknown"  # no site search was performed here
    assert all(word not in str(decision.signals).lower() for word in ("lent", "prêt à acheter", "douleur"))


def test_outside_the_zone_and_suppressed_or_duplicate_entities_are_excluded():
    outside = qualified(build_candidate(listing(lat=48.0, lon=2.0)))
    assert outside.stage == "excluded" and outside.reason == "unverifiable_location"
    assert qualified(build_candidate(listing()), suppressed=True).reason == "suppressed"
    assert qualified(build_candidate(listing()), already_seen=True).reason == "duplicate"


def test_old_provenance_is_not_presented_as_a_current_observation():
    stale = qualified(build_candidate(listing(last_updated=date.min)))
    assert stale.stage == "enriched" and not stale.checks["fresh_provenance"]
    observed_only = qualified(build_candidate(listing(last_updated=None)))
    assert observed_only.checks["freshness_basis"] == "observed_at"


def test_dedupe_merges_two_sources_about_the_same_establishment():
    first = build_candidate(listing())
    second = build_candidate(listing(external_id="osm/node/9", source_name="osm", source_url="https://osm.org/node/9"))
    merged = dedupe([first, second])
    assert len(merged) == 1 and len(merged[0].all_listings) == 2
    assert all(s["key"] for s in qualified(merged[0]).signals)


def test_an_inactive_mandate_runs_nothing_and_touches_no_provider():
    class Adapter:
        name = "fake"
        verticals = ("restaurants",)
        max_radius_m = 10_000

        def fetch(self, params):
            raise AssertionError("a draft mandate must never call a provider")

    mandate = Mandate(
        status="draft",
        zone=ZONE,
        sector="restaurants",
        offer="offre",
        daily_volume=10,
        total_volume=100,
        ai_budget=0,
        cadence_minutes=60,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    with pytest.raises(engine.MandateNotRunnable):
        import asyncio

        asyncio.run(engine.run_mandate_discovery(None, mandate, adapters=[Adapter()]))


def test_due_respects_the_mandate_cadence_and_first_run():
    now = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
    assert engine.is_due(None, 60, now)
    assert not engine.is_due(now - timedelta(minutes=30), 60, now)
    assert engine.is_due(now - timedelta(minutes=61), 60, now)


def test_the_task_skips_network_when_external_sources_is_off(monkeypatch):
    from tasks.outreach_mandate_tasks import run_due_mandate_discovery

    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES", raising=False)
    result = run_due_mandate_discovery.run()
    assert result == {"skipped": "FEATURE_EXTERNAL_SOURCES is off"}


def test_batch_progress_endpoints_are_registered_under_the_api_prefix():
    from server import app

    paths = app.openapi()["paths"]
    assert "/api/outreach-mandates/{mandate_id}/batches" in paths
    assert "/api/outreach-mandates/{mandate_id}/batches/{batch_id}/items" in paths
