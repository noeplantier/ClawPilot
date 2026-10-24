"""Map routes that need a running API: login guard and the organisation's own prospect layer.
The job pipeline (OpenStreetMap search) is covered in test_map_job_pipeline.py with a fake source: no network."""

import json
import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
AREA = dict(south=45.75, west=4.82, north=45.77, east=4.85, category="restaurants")


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
