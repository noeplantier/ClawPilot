"""Discovery adapters, geometry, parameter checks and the run store. Fixtures only: no socket is ever opened."""

import json
import uuid
from pathlib import Path

import pytest

from services import discovery_runs
from services.outreach_os import discovery as d
from services.outreach_os import source_adapters as sa
from services.outreach_os.types import RawListing

FIX = Path(__file__).resolve().parent.parent / "fixtures"
OSM = json.loads((FIX / "osm" / "overpass_lyon.json").read_text())
REGISTRY = json.loads((FIX / "registry" / "search_lyon.json").read_text())
LYON = {"lat": 45.764, "lon": 4.8357}


def params(**kw):
    return d.SourceParams(**{"vertical": "restaurants", "limit": 25, **kw})


# ------------------------------------------------------------------ world fixture
def test_the_world_fixture_covers_every_continent_and_vertical_without_a_network():
    world = d.WorldFixtureAdapter()
    records = world._records()
    assert len({r["country"] for r in records}) >= 15 and {r["vertical"] for r in records} == set(d.VERTICALS)
    assert {"FR", "US", "BR", "NG", "JP", "AU", "ZA", "AE"} <= {r["country"] for r in records}
    assert all((r["email"] or "").endswith(".example") or r["email"] is None for r in records)  # never a real address


def test_filters_by_vertical_country_city_and_radius():
    world = d.WorldFixtureAdapter()
    everything = world.fetch(params(vertical="hotels", limit=100)).listings
    assert everything and all(item.category == "hotel" for item in everything)
    france = world.fetch(params(vertical="hotels", country="FR")).listings
    assert all(item.city in ("Lyon", "Paris") for item in france)
    near = world.fetch(params(vertical="restaurants", **LYON, radius_m=5000)).listings
    assert near and all(d.haversine_m(LYON["lat"], LYON["lon"], i.lat, i.lon) <= 5000 for i in near)
    assert world.fetch(params(vertical="restaurants", city="Atlantis")).listings == []


def test_every_listing_keeps_its_provenance_and_raw_record():
    item = d.WorldFixtureAdapter().fetch(params(vertical="bakeries", limit=100)).listings[0]
    assert item.source_name == "world_fixture" and item.source_url.startswith("fixture://world/")
    assert item.raw and item.raw["external_id"] == item.external_id


def test_the_planted_duplicate_is_merged_once():
    result = d.WorldFixtureAdapter().fetch(params(vertical="restaurants", city="Lyon", limit=100))
    ids = {i.external_id for i in result.listings}
    assert "wf-dup" in ids and len(ids) >= 2
    unique, merged = d.dedupe_listings(result.listings)
    assert merged == 1 and len(unique) == len(result.listings) - 1  # one business, one listing


def test_the_digest_is_stable_and_changes_with_the_data():
    a = d.raw_digest([{"x": 1}])
    assert a == d.raw_digest([{"x": 1}]) and a != d.raw_digest([{"x": 2}]) and a[1] > 0


def test_an_oversized_raw_record_is_replaced_by_a_marker():
    assert d.cap_raw({"k": "v"}) == {"k": "v"}
    assert d.cap_raw({"k": "x" * 5000}).get("_truncated") is True


# ------------------------------------------------------------------ parameter checks
@pytest.mark.parametrize(
    "kw",
    [
        {"vertical": "weapons"},
        {"limit": 0},
        {"limit": 101},
        {"lat": 45.0},
        {"lat": 45.0, "lon": 4.0, "radius_m": 50},
    ],
)
def test_bad_parameters_are_refused_with_a_reason(kw):
    with pytest.raises(d.BadParams):
        d.check_params(d.WorldFixtureAdapter(), params(**kw))


def test_a_network_provider_needs_a_position_and_respects_its_radius():
    osm_adapter = sa.OsmAdapter(lambda q: OSM)
    with pytest.raises(d.BadParams, match="position"):
        d.check_params(osm_adapter, params())
    with pytest.raises(d.BadParams, match="radius"):
        d.check_params(osm_adapter, params(**LYON, radius_m=osm_adapter.max_radius_m + 1))
    d.check_params(osm_adapter, params(**LYON, radius_m=3000))
    with pytest.raises(d.BadParams, match="does not cover"):
        d.check_params(sa.FrenchRegistryAdapter(lambda p: REGISTRY), params(vertical="crafts", **LYON))


# ------------------------------------------------------------------ OpenStreetMap
def test_osm_adapter_keeps_the_asked_circle_and_the_tags_it_read():
    seen = []

    def fetch(query):
        seen.append(query)
        return OSM

    result = sa.OsmAdapter(fetch).fetch(params(**LYON, radius_m=2000))
    names = {i.name for i in result.listings}
    assert "Boulangerie Martin" in names
    assert "[out:json]" in seen[0] and "out center meta 300" in seen[0]
    marcel = next(i for i in result.listings if i.external_id == "node/101")
    assert marcel.raw["osm"] == "node/101" and "tags" in marcel.raw and result.raw_sha256
    far = sa.OsmAdapter(fetch).fetch(params(lat=45.7640, lon=4.8357, radius_m=100))
    assert all(d.haversine_m(45.764, 4.8357, i.lat, i.lon) <= 100 for i in far.listings)


# ------------------------------------------------------------------ French registry
def test_the_registry_adapter_keeps_what_is_published_and_leaves_the_rest_unknown():
    calls = []

    def fetch_page(p):
        calls.append(p)
        return REGISTRY

    result = sa.FrenchRegistryAdapter(fetch_page).fetch(params(vertical="bakeries", **LYON, radius_m=4000))
    assert [i.external_id for i in result.listings] == ["siren/123456782", "siren/234567891", "siren/456789123"]
    first = result.listings[0]
    assert first.email is None and first.phone is None and first.website is None  # the registry publishes none
    assert (first.lat, first.lon) == (45.7595, 4.833) and first.last_updated.isoformat() == "2026-08-20"
    assert first.source_url.endswith("/entreprise/123456782") and first.raw["siren"] == "123456782"
    assert result.listings[2].lat is None  # unparseable coordinates stay empty
    assert calls[0]["activite_principale"] == sa.NAF_BY_VERTICAL["bakeries"] and calls[0]["radius"] == 4


def test_the_registry_adapter_pages_politely_and_stops_on_a_short_page():
    page = [{"siren": str(100000000 + n), "nom_complet": f"CO {n}", "siege": {}} for n in range(25)]
    asked = []

    def fetch_page(p):
        asked.append(p["page"])
        return {"results": page if p["page"] == 1 else page[:3], "total_results": 60}

    result = sa.FrenchRegistryAdapter(fetch_page).fetch(params(vertical="restaurants", **LYON, limit=75))
    assert asked == [1, 2] and len(result.listings) == 28 and result.truncated is True


# ------------------------------------------------------------------ run store
def _run(account, listings=()):
    return discovery_runs.Run(uuid.uuid4(), account, "world_fixture", "restaurants", None, list(listings), 0, False)


def test_a_run_is_only_visible_to_its_organisation_and_expires():
    now = [0.0]
    store = discovery_runs.RunStore(clock=lambda: now[0])
    mine, other = uuid.uuid4(), uuid.uuid4()
    run = _run(mine)
    store.put(run)
    assert store.get(mine, run.id) is run and store.get(other, run.id) is None
    now[0] = discovery_runs.TTL_SECONDS + 1
    assert store.get(mine, run.id) is None


def test_the_run_store_is_bounded():
    store = discovery_runs.RunStore()
    first = _run(uuid.uuid4())
    store.put(first)
    for _ in range(discovery_runs.MAX_RUNS):
        store.put(_run(uuid.uuid4()))
    assert store.get(first.account_id, first.id) is None


def test_a_listing_with_raw_data_round_trips_through_the_stored_fields():
    from repositories.prospect_repo import _fields_of

    with_raw = RawListing("a", "A", "s", "u", raw={"k": 1}, lat=1.0, lon=2.0)
    without = RawListing("a", "A", "s", "u")
    assert _fields_of(with_raw)["raw"] == {"k": 1}
    assert not {"raw", "lat", "lon"} & set(_fields_of(without))  # rows (and hashes) of older sources are unchanged
