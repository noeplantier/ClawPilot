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
