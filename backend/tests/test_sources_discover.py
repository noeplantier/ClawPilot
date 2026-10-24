"""Discovery sources end to end: the world demo over HTTP (no flag, no network), the network providers in-process with
their HTTP clients replaced by fixtures. Limits are tested in-process with their own addresses and users so that
tests never consume each other's budget."""

import json
import os
import types
import uuid
from pathlib import Path

import pytest
import requests
from fastapi import HTTPException
from sqlalchemy import select

from db.models import AuditLog
from models import AddFromRunIn, DiscoverIn
from routes import sources
from tasks._bridge import run_async

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
FIX = Path(__file__).parent / "fixtures"
OSM = json.loads((FIX / "osm" / "overpass_lyon.json").read_text())
REGISTRY = json.loads((FIX / "registry" / "search_lyon.json").read_text())
LYON = dict(lat=45.764, lon=4.8357, radius_m=3000, country="FR")


def _register():
    uid = uuid.uuid4().hex[:10]
    token = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"src_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "S",
            "organization_name": f"S {uid}",
        },
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = requests.get(f"{API}/auth/me", headers=headers).json()["user"]
    return headers, me


@pytest.fixture()
def org():
    return _register()


def _request(ip=None):
    return types.SimpleNamespace(
        client=types.SimpleNamespace(host=ip or f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.1")
    )


def _discover(me, ip=None, **kw):
    payload = DiscoverIn(**{"provider": "world_fixture", "vertical": "restaurants", "limit": 10, **kw})

    async def go(session):
        return await sources.discover(payload, _request(ip), user=me, session=session)

    return run_async(go)


def _add(me, run_id, ids, **kw):
    payload = AddFromRunIn(external_ids=ids, **kw)

    async def go(session):
        return await sources.add_from_run(run_id, payload, user=me, session=session)

    return run_async(go)


def _audit(account_id, action):
    async def go(session):
        rows = await session.execute(
            select(AuditLog).where(AuditLog.account_id == account_id, AuditLog.action == action)
        )
        return [r.diff for r in rows.scalars()]

    return run_async(go)


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for flag in ("FEATURE_EXTERNAL_SOURCES", "FEATURE_PROSPECT_IMPORT"):
        monkeypatch.delenv(flag, raising=False)


# ---------------------------------------------------------------- HTTP, no flag, no network
def test_the_provider_list_says_what_is_available_and_what_it_costs(org):
    headers, _ = org
    assert requests.get(f"{API}/sources").status_code in (401, 403)
    items = {s["name"]: s for s in requests.get(f"{API}/sources", headers=headers).json()}
    assert set(items) == {"world_fixture", "openstreetmap", "registry_fr"}
    assert items["world_fixture"]["available"] is True and items["world_fixture"]["needs_position"] is False
    assert (
        items["openstreetmap"]["available"] is False
        and "FEATURE_EXTERNAL_SOURCES" in items["openstreetmap"]["unavailable_reason"]
    )
    assert all(
        s["cost"] == "free, no key" and s["license_note"] and s["rate_limit_per_minute"] > 0 for s in items.values()
    )


def test_the_world_demo_discovers_deduplicated_places_with_explained_signals(org):
    headers, _ = org
    resp = requests.post(
        f"{API}/sources/discover",
        headers=headers,
        json={"provider": "world_fixture", "vertical": "restaurants", "limit": 50},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["total"] >= 5 and out["duplicates_merged"] >= 0 and out["places"] and out["run_id"]
    place = out["places"][0]
    assert place["source_name"] == "world_fixture" and place["source_url"].startswith("fixture://")
    keys = {s["key"] for s in place["signals"]}
    assert {"no_website", "website_unreachable", "stale_listing"} <= keys
    assert all(s["evidence"] for s in place["signals"])  # every signal says why
    page2 = requests.get(
        f"{API}/sources/runs/{out['run_id']}", headers=headers, params={"offset": 2, "limit": 2}
    ).json()
    assert page2["offset"] == 2 and len(page2["places"]) == 2 and page2["total"] == out["total"]


def test_bad_input_is_refused_before_anything_runs(org):
    headers, _ = org
    for body in (
        {"provider": "nope", "vertical": "restaurants"},
        {"provider": "world_fixture", "vertical": "weapons"},
        {"provider": "world_fixture", "vertical": "restaurants", "limit": 500},
        {"provider": "world_fixture", "vertical": "restaurants", "lat": 45.0},
        {"provider": "world_fixture", "vertical": "restaurants", "country": "france"},
    ):
        assert requests.post(f"{API}/sources/discover", headers=headers, json=body).status_code == 422, body


def test_a_run_belongs_to_its_organisation(org):
    headers, _ = org
    run = requests.post(
        f"{API}/sources/discover", headers=headers, json={"provider": "world_fixture", "vertical": "hotels"}
    ).json()
    other, _ = _register()
    assert requests.get(f"{API}/sources/runs/{run['run_id']}", headers=other).status_code == 410
    assert requests.get(f"{API}/sources/runs/{uuid.uuid4()}", headers=headers).status_code == 410


# ---------------------------------------------------------------- in-process: flags, limits, audit
def test_network_providers_are_refused_while_external_sources_are_off_and_the_refusal_is_audited(org):
    _, me = org
    with pytest.raises(HTTPException) as refused:
        _discover(me, provider="openstreetmap", **LYON)
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "provider_disabled"
    assert _audit(uuid.UUID(me["org_id"]), "sources.refused")[0]["provider"] == "openstreetmap"


def test_every_discovery_is_audited_with_parameters_counts_and_the_raw_digest_never_the_places(org):
    _, me = org
    out = _discover(me, vertical="bakeries", limit=20)
    entry = _audit(uuid.UUID(me["org_id"]), "sources.discover")[0]
    assert entry["provider"] == "world_fixture" and entry["results"] == out.total and len(entry["raw_sha256"]) == 64
    assert entry["raw_bytes"] > 0 and entry["licence"] and "name" not in json.dumps(entry).lower().replace("raw", "")


def test_the_user_limit_stops_a_burst_and_the_refusal_is_audited(org):
    _, me = org
    for _ in range(20):
        _discover(me)
    with pytest.raises(HTTPException) as limited:
        _discover(me)
    assert limited.value.status_code == 429 and limited.value.detail["code"] == "rate_limited_user"
    assert int(limited.value.headers["Retry-After"]) >= 1
    assert any(e["code"] == "rate_limited_user" for e in _audit(uuid.UUID(me["org_id"]), "sources.refused"))


def test_the_ip_limit_applies_across_users():
    ip = f"198.51.100.{uuid.uuid4().int % 250}"
    users = [_register()[1] for _ in range(2)]
    for i in range(30):
        _discover(users[i % 2], ip=ip)
    with pytest.raises(HTTPException) as limited:
        _discover(users[0], ip=ip)
    assert limited.value.status_code == 429 and limited.value.detail["code"] == "rate_limited_ip"


# ---------------------------------------------------------------- in-process: network providers on fixtures
def test_openstreetmap_runs_on_a_fixture_and_asks_for_a_country(monkeypatch, org):
    _, me = org
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    monkeypatch.setattr(sources.overpass_svc, "default_fetcher", lambda q: OSM)
    with pytest.raises(HTTPException) as no_country:
        _discover(me, provider="openstreetmap", lat=45.764, lon=4.8357, radius_m=3000)
    assert no_country.value.status_code == 422 and "country" in no_country.value.detail["message"]
    out = _discover(me, provider="openstreetmap", **LYON)
    assert out.total >= 1 and "ODbL" in out.license_note
    unknown = next(s for s in out.places[0].signals if s.key == "no_website")
    assert out.places[0].website or unknown.state in (
        "unknown",
        "not_detected",
    )  # never "no website" from an empty OSM tag


def test_the_registry_never_invents_contacts_and_provider_trouble_is_a_502(monkeypatch, org):
    _, me = org
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    monkeypatch.setattr(sources.registry_svc, "fetch_page", lambda p: REGISTRY)
    out = _discover(me, provider="registry_fr", vertical="bakeries", **LYON)
    assert {p.external_id for p in out.places} == {"siren/123456782", "siren/234567891", "siren/456789123"}
    assert all(p.email is None and p.phone is None and p.website is None for p in out.places)
    assert all(next(s for s in p.signals if s.key == "no_website").state == "unknown" for p in out.places)

    def down(params):
        raise sources.registry_svc.Unavailable("the company registry answered HTTP 429; try again in a minute")

    monkeypatch.setattr(sources.registry_svc, "fetch_page", down)
    with pytest.raises(HTTPException) as err:
        _discover(me, provider="registry_fr", vertical="bakeries", **LYON)
    assert err.value.status_code == 502 and err.value.detail["code"] == "provider_unavailable"


# ---------------------------------------------------------------- adding to the prospects
def test_adding_needs_an_attestation_and_a_selection_from_the_run(org):
    headers, me = org
    out = _discover(me, vertical="restaurants", limit=5)
    ids = [p.external_id for p in out.places[:2]]
    with pytest.raises(HTTPException) as no_attest:
        _add(me, out.run_id, ids)
    assert no_attest.value.status_code == 422 and no_attest.value.detail["code"] == "attestation_required"
    with pytest.raises(HTTPException) as foreign:
        _add(me, out.run_id, ["not-in-the-run"], attestation=True)
    assert foreign.value.detail["code"] == "unknown_selection"
    assert requests.get(f"{API}/prospects", headers=headers).json()["items"] == []


def test_the_demo_places_become_prospects_pending_review_with_their_provenance(org):
    headers, me = org
    out = _discover(me, vertical="restaurants", limit=6)
    ids = [p.external_id for p in out.places[:3]]
    added = _add(me, out.run_id, ids, attestation=True)
    assert added.created == 3 and added.suppressed == 0
    items = requests.get(f"{API}/prospects", headers=headers, params={"limit": 50}).json()["items"]
    assert len(items) == 3 and all(p["review_status"] == "pending" for p in items)
    detail = requests.get(f"{API}/prospects/{items[0]['id']}", headers=headers).json()
    assert detail["sources"][0]["source_name"] == "world_fixture" and detail["sources"][0]["license_note"]
    assert _audit(uuid.UUID(me["org_id"]), "sources.added")[0]["selected"] == 3
    again = _add(me, out.run_id, ids, attestation=True)  # idempotent: the same places are updated, not duplicated
    assert again.created == 0 and again.updated == 3


def test_real_data_needs_the_import_flag_and_a_site_check_needs_the_external_flag(monkeypatch, org):
    _, me = org
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    monkeypatch.setattr(sources.overpass_svc, "default_fetcher", lambda q: OSM)
    out = _discover(me, provider="openstreetmap", **LYON)
    ids = [p.external_id for p in out.places[:1]]
    with pytest.raises(HTTPException) as closed:
        _add(me, out.run_id, ids, attestation=True)
    assert closed.value.status_code == 403 and closed.value.detail["code"] == "feature_disabled"
    monkeypatch.setenv("FEATURE_PROSPECT_IMPORT", "true")
    assert _add(me, out.run_id, ids, attestation=True).created == 1
    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES")
    with pytest.raises(HTTPException) as no_sites:
        _add(me, out.run_id, ids, attestation=True, check_websites=True)
    assert no_sites.value.detail["code"] == "external_sources_disabled"
