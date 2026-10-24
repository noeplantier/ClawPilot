"""One click on a map point: the place becomes a prospect and joins the CRM, through the same attested import.

The route is called in-process with the import flag set (the test server keeps it off, like production defaults);
the results are read back over HTTP. No network: websites are not fetched here (`check_website=False`).
"""

import os
import uuid

import pytest
import requests
from fastapi import HTTPException

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"qa_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Quick Add",
            "organization_name": f"QA {uid}",
        },
    ).json()
    h = {"Authorization": f"Bearer {reg['access_token']}"}
    return uid, h, requests.get(f"{API}/auth/me", headers=h).json()["user"]


def _place(uid, **over):
    base = {
        "external_id": f"node/{uid}",
        "name": f"Chez Test {uid}",
        "lat": 45.76,
        "lon": 4.83,
        "category": "restaurants",
        "address": "1 rue de la République",
        "postcode": "69002",
        "city": "Lyon",
        "phone": "+33 4 78 00 00 01",
        "email": f"contact_{uid}@chez-test.example",
        "website": f"https://chez-test-{uid}.example",
        "source_url": f"https://www.openstreetmap.org/node/{uid}",
    }
    return {**base, **over}


def _add(me, place, **opts):
    from models import MapAddIn
    from routes import map_search
    from tasks._bridge import run_async

    payload = MapAddIn(place=place, attestation=opts.pop("attestation", True), check_website=False, **opts)
    os.environ["FEATURE_PROSPECT_IMPORT"] = "true"
    try:

        async def go(session):
            return await map_search.add_place(payload, user=me, session=session)

        return run_async(go)
    finally:
        del os.environ["FEATURE_PROSPECT_IMPORT"]


def test_one_click_puts_the_business_in_the_crm_with_what_the_map_published():
    uid, h, me = _org()
    out = _add(me, _place(uid))
    assert out.created and out.in_crm and out.review_status == "approved"
    assert out.email == f"contact_{uid}@chez-test.example" and out.phone and out.website
    assert out.email_found_on_site is False and out.website_checked is False  # nothing was read from the site
    assert out.heat is not None and out.heat.info_pct > 0

    crm = requests.get(f"{API}/leads", headers=h).json()  # the CRM page lists the prospect, with where it stands
    assert [(lead["full_name"], lead["review_status"]) for lead in crm] == [(f"Chez Test {uid}", "approved")]
    assert crm[0]["city"] == "Lyon" and crm[0]["website"] and crm[0]["heat"]["info_pct"] > 0
    on_map = requests.get(f"{API}/map/prospects", headers=h).json()
    assert [(p["name"], p["review_status"]) for p in on_map] == [(f"Chez Test {uid}", "approved")]
    detail = requests.get(f"{API}/prospects/{out.lead_id}", headers=h).json()
    assert detail["sources"][0]["source_url"].startswith("https://www.openstreetmap.org/")  # provenance kept
    events = requests.get(f"{API}/prospects/{out.lead_id}/events", headers=h).json()
    assert any(e.get("label") == "Approved by a reviewer" or "approv" in str(e).lower() for e in events)


def test_without_approval_the_place_waits_in_the_review_queue_and_says_so_in_the_crm():
    uid, h, me = _org()
    out = _add(me, _place(uid), approve=False)
    assert out.review_status == "pending" and out.in_crm is False
    assert [lead["review_status"] for lead in requests.get(f"{API}/leads", headers=h).json()] == ["pending"]
    queue = requests.get(f"{API}/prospects", params={"review_status": "pending"}, headers=h).json()
    assert queue["total"] == 1 and queue["items"][0]["id"] == out.lead_id


def test_adding_the_same_place_twice_completes_it_and_never_duplicates():
    uid, h, me = _org()
    first = _add(me, _place(uid, email=None, phone=None))
    second = _add(me, _place(uid))
    assert first.lead_id == second.lead_id and first.created and not second.created
    assert len(requests.get(f"{API}/leads", headers=h).json()) == 1


def test_it_refuses_without_the_attestation_and_without_the_import_flag():
    uid, h, me = _org()
    with pytest.raises(HTTPException) as no_attest:
        _add(me, _place(uid), attestation=False)
    assert no_attest.value.status_code == 422 and no_attest.value.detail["code"] == "attestation_required"
    assert requests.get(f"{API}/leads", headers=h).json() == []  # nothing was written

    body = {"place": _place(uid), "attestation": True, "check_website": False}
    off = requests.post(f"{API}/map/places/add", headers=h, json=body)  # the test server keeps the flag off
    assert off.status_code == 403 and off.json()["detail"]["code"] == "feature_disabled"


def test_a_business_on_the_suppression_list_is_not_added():
    uid, h, me = _org()
    address = f"contact_{uid}@chez-test.example"
    assert requests.post(f"{API}/prospects/suppressions", headers=h, json={"email": address}).status_code in (200, 201)
    with pytest.raises(HTTPException) as refused:
        _add(me, _place(uid))
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "suppressed"
    assert requests.get(f"{API}/leads", headers=h).json() == []


def test_the_route_needs_a_login_and_a_readable_place():
    uid, h, _ = _org()
    assert requests.post(f"{API}/map/places/add", json={"place": _place(uid), "attestation": True}).status_code in (
        401,
        403,
    )
    bad = requests.post(
        f"{API}/map/places/add", headers=h, json={"place": {**_place(uid), "lat": 999}, "attestation": True}
    )
    assert bad.status_code == 422
