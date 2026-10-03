"""Live map search route (OpenStreetMap): flag, limits, shape, rate limit. Overpass is replaced: no network."""

import json
import os
import uuid
from pathlib import Path

import pytest
import requests
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from models import MapSearchIn  # noqa: E402
from routes import map_search  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "osm" / "overpass_lyon.json").read_text())
AREA = dict(south=45.75, west=4.82, north=45.77, east=4.85, category="restaurants")


def _user():
    return {"org_id": str(uuid.uuid4()), "id": str(uuid.uuid4()), "role": "owner"}


def _call(payload, user):
    import asyncio

    return asyncio.run(map_search.search(MapSearchIn(**payload), user=user))


def test_the_search_is_closed_while_external_sources_are_off(monkeypatch):
    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES", raising=False)
    with pytest.raises(HTTPException) as refused:
        _call(AREA, _user())
    assert refused.value.status_code == 409


def test_a_search_returns_real_places_with_attribution_and_no_invented_field(monkeypatch):
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    seen = []
    monkeypatch.setattr(map_search.overpass_svc, "default_fetcher", lambda q: seen.append(q) or FIXTURE)
    out = _call(AREA, _user())
    assert "OpenStreetMap" in out.attribution and "ODbL" in out.license_note and out.truncated is False
    names = {p.name: p for p in out.places}
    assert len(out.places) == 3 and all(-90 < p.lat < 90 and -180 < p.lon < 180 for p in out.places)
    assert names["Boulangerie Martin"].email is None and names["Boulangerie Martin"].phone is None
    assert "nwr" in seen[0] and "(45.75000,4.82000,45.77000,4.85000)" in seen[0]


def test_an_area_too_large_or_an_unknown_category_is_refused_before_any_request(monkeypatch):
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    monkeypatch.setattr(map_search.overpass_svc, "default_fetcher", lambda q: pytest.fail("must not be called"))
    for bad in ({**AREA, "south": 44.0}, {**AREA, "category": "weapons"}, {**AREA, "south": 45.9, "north": 45.8}):
        with pytest.raises(HTTPException) as refused:
            _call(bad, _user())
        assert refused.value.status_code == 422


def test_overpass_trouble_is_a_502_and_the_rate_limit_is_per_organisation(monkeypatch):
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")

    def down(query):
        raise map_search.overpass_svc.Unavailable("busy")

    monkeypatch.setattr(map_search.overpass_svc, "default_fetcher", down)
    user = _user()
    with pytest.raises(HTTPException) as err:
        _call(AREA, user)
    assert err.value.status_code == 502
    for _ in range(5):
        with pytest.raises(HTTPException):
            _call(AREA, user)
    with pytest.raises(HTTPException) as limited:
        _call(AREA, user)
    assert limited.value.status_code == 429
    with pytest.raises(HTTPException) as other:
        _call(AREA, _user())
    assert other.value.status_code == 502  # another organisation is not limited by the first one


def test_the_endpoint_needs_a_login_over_http():
    assert requests.post(f"{API}/map/search", json=AREA).status_code in (401, 403)


def test_my_prospects_layer_lists_only_this_organisations_positioned_prospects():
    """Import a small JSON list with and without positions (through the real endpoint with the flag set in-process)."""
    from models import ImportIn
    from routes import prospect_imports
    from tasks._bridge import run_async

    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"mp_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "M",
            "organization_name": f"M {uid}",
        },
    ).json()
    h = {"Authorization": f"Bearer {reg['access_token']}"}
    me = requests.get(f"{API}/auth/me", headers=h).json()["user"]
    rows = [
        {
            "name": f"Placé {uid}",
            "city": "Lyon",
            "lat": 45.76,
            "lon": 4.83,
            "external_id": f"node/{uid}",
            "email": f"p_{uid}@pose.example",
        },
        {"name": f"Sans position {uid}", "city": "Paris", "external_id": f"node/np{uid}"},
    ]
    os.environ["FEATURE_PROSPECT_IMPORT"] = "true"
    try:
        payload = ImportIn(
            format="json",
            content=json.dumps(rows),
            origin="A list typed by hand for this test",
            legal_basis="legitimate_interest_b2b",
            preview=False,
            attestation=True,
        )

        async def go(session):
            return await prospect_imports.import_prospects(payload, user=me, session=session)

        run_async(go)
    finally:
        del os.environ["FEATURE_PROSPECT_IMPORT"]
    layer = requests.get(f"{API}/map/prospects", headers=h)
    assert layer.status_code == 200, layer.text
    items = layer.json()
    assert [p["name"] for p in items] == [f"Placé {uid}"]  # no position, no pin
    assert (items[0]["lat"], items[0]["lon"], items[0]["review_status"], items[0]["has_email"]) == (
        45.76,
        4.83,
        "pending",
        True,
    )
    assert items[0]["external_id"] == f"node/{uid}"
    assert items[0]["signals"] == ["public_contact_present"]  # the imported e-mail; nothing else is claimed
    assert items[0]["score"] is not None and items[0]["created_at"]
    assert items[0]["country"] == "FR" and items[0]["vertical"]
    other = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"mq_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Q",
            "organization_name": f"Q {uid}",
        },
    ).json()["access_token"]
    assert requests.get(f"{API}/map/prospects", headers={"Authorization": f"Bearer {other}"}).json() == []  # isolation
    assert requests.get(f"{API}/map/prospects").status_code in (401, 403)


def test_browser_path_query_then_parse_gives_the_same_places_as_a_server_search(monkeypatch):
    import asyncio

    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    user = _user()
    out = asyncio.run(map_search.query(MapSearchIn(**AREA), user=user))
    assert out.query.startswith("[out:json]") and out.endpoints and all(e.startswith("https://") for e in out.endpoints)
    parsed = asyncio.run(map_search.parse(map_search.MapParseIn(data=FIXTURE), user=user))
    monkeypatch.setattr(map_search.overpass_svc, "default_fetcher", lambda q: FIXTURE)
    direct = _call(AREA, _user())
    assert [p.external_id for p in parsed.places] == [p.external_id for p in direct.places]
    assert parsed.places and all(p.source_url.startswith("https://www.openstreetmap.org/") for p in parsed.places)


def test_the_browser_path_is_closed_without_the_flag_and_validates_its_input(monkeypatch):
    import asyncio

    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES", raising=False)
    with pytest.raises(HTTPException) as closed:
        asyncio.run(map_search.query(MapSearchIn(**AREA), user=_user()))
    assert closed.value.status_code == 409
    with pytest.raises(HTTPException) as closed_parse:
        asyncio.run(map_search.parse(map_search.MapParseIn(data=FIXTURE), user=_user()))
    assert closed_parse.value.status_code == 409
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    with pytest.raises(HTTPException) as wide:
        asyncio.run(
            map_search.query(MapSearchIn(south=40, west=0, north=50, east=10, category="restaurants"), user=_user())
        )
    assert wide.value.status_code == 422
    for bad in ({}, {"elements": "x"}, {"elements": [{}] * (map_search.MAX_PARSED_ELEMENTS + 1)}):
        with pytest.raises(HTTPException) as refused:
            asyncio.run(map_search.parse(map_search.MapParseIn(data=bad), user=_user()))
        assert refused.value.status_code == 422


def test_parse_is_rate_limited_per_organisation(monkeypatch):
    import asyncio

    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    user = _user()
    for _ in range(12):
        asyncio.run(map_search.parse(map_search.MapParseIn(data={"elements": []}), user=user))
    with pytest.raises(HTTPException) as limited:
        asyncio.run(map_search.parse(map_search.MapParseIn(data={"elements": []}), user=user))
    assert limited.value.status_code == 429
