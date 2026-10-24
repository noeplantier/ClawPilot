"""GET /map/cities: leads counted per town and heat tier, for the dropdown of the map's town search.

Rows are written in-process (a CRM lead cannot carry a city through POST /leads); the answer is read back over HTTP and
compared with the Python heat rule, so the SQL tiers cannot drift from the figures shown elsewhere.
"""

import os
import uuid
from datetime import datetime, timezone

import requests

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from db.models import Lead  # noqa: E402
from services.outreach_os import cities
from services.outreach_os import heat as heat_rules  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
FULL = {
    "email": "{n}@full.example",
    "phone": "+33 4 78 00 00 01",
    "website": "https://full.example",
    "company": "Full SAS",
    "vertical": "restaurants",
    "country": "FR",
    "title": "Owner",
}  # all eight tracked fields known: heat 100, hot


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"cities_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Cities",
            "organization_name": f"Cities {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return h, requests.get(f"{API}/auth/me", headers=h).json()["user"]


def _full(n):
    return {k: v.format(n=n) for k, v in FULL.items()}


def _insert(account, rows):
    async def go(session):
        for r in rows:
            session.add(Lead(account_id=account, **r))
        await session.flush()

    run_async(go)


def _asked(h):
    resp = requests.get(f"{API}/map/cities", headers=h)
    assert resp.status_code == 200, resp.text
    return {c["key"]: c for c in resp.json()}


def test_leads_are_counted_per_town_by_heat_tier_whatever_the_spelling():
    h, me = _org()
    account = uuid.UUID(me["org_id"])
    _insert(
        account,
        [
            {"full_name": "Hot 1", "city": "Lyon", **_full(1)},
            {"full_name": "Hot 2", "city": "lyon ", **_full(2)},
            {"full_name": "Cold 1", "city": "LYON"},
            {
                "full_name": "Warm 1",
                "city": "Saint-Étienne",
                "email": "w@w.example",
                "phone": "+33 4 77 00 00 01",
                "company": "W SAS",
            },
            {"full_name": "Hot 3", "city": "St Etienne", **_full(3)},
            {"full_name": "Scored", "city": "Nantes", "email": "s@s.example", "score": 90},
        ],
    )
    out = _asked(h)
    assert out["lyon"] == {"city": "Lyon", "key": "lyon", "hot": 2, "warm": 0, "cold": 1, "total": 3}
    assert (out["saint etienne"]["hot"], out["saint etienne"]["total"]) == (1, 2)
    # a CRM score of 0 means "not scored"; a real one lifts the lead: (90 + 25 + 1) // 2 = 58 is warm, never hot
    assert (out["nantes"]["hot"], out["nantes"]["warm"]) == (0, 1)
    hottest = requests.get(f"{API}/map/cities", headers=h).json()
    assert [c["key"] for c in hottest][:2] == ["lyon", "saint etienne"]  # most hot leads first


def test_a_town_without_a_value_a_rejected_prospect_or_a_deleted_lead_is_not_counted():
    h, me = _org()
    account = uuid.UUID(me["org_id"])
    _insert(
        account,
        [
            {"full_name": "No city", **_full(1)},
            {"full_name": "Unknown city", "city": "unknown", **_full(2)},
            {"full_name": "Unspecified", "city": "Unspecified", **_full(3)},
            {"full_name": "Rejected", "city": "Rouen", "review_status": "rejected", **_full(4)},
            {"full_name": "Deleted", "city": "Rouen", "deleted_at": datetime.now(timezone.utc), **_full(5)},
            {"full_name": "Pending", "city": "Rouen", "review_status": "pending", **_full(6)},
            {"full_name": "Approved", "city": "Rouen", "review_status": "approved", **_full(7)},
        ],
    )
    assert _asked(h) == {"rouen": {"city": "Rouen", "key": "rouen", "hot": 2, "warm": 0, "cold": 0, "total": 2}}


def test_the_figures_of_a_discovery_run_equal_the_heat_shown_on_every_prospect():
    h, _ = _org()
    assert requests.post(f"{API}/prospects/discovery/run", headers=h, json={}).status_code == 200
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    assert len(items) > 3
    expected = cities.merge(
        (i["city"], i["heat"]["tier"], 1) for i in items if i["city"] and heat_rules.is_known(i["city"])
    )
    got = requests.get(f"{API}/map/cities", headers=h).json()
    assert got == expected and got  # the same towns, the same tiers, the same order: counted from the same rule
    assert sum(c["total"] for c in got) <= len(items)


def test_rejecting_a_prospect_takes_it_out_of_the_count_of_its_town():
    h, _ = _org()
    requests.post(f"{API}/prospects/discovery/run", headers=h, json={})
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    target = next(i for i in items if i["city"] and heat_rules.is_known(i["city"]))
    key = cities.fold(target["city"])
    before = _asked(h)[key]["total"]
    resp = requests.post(f"{API}/prospects/{target['id']}/review", headers=h, json={"decision": "reject"})
    assert resp.status_code == 200, resp.text
    after = _asked(h).get(key)
    assert (after["total"] if after else 0) == before - 1


def test_each_organisation_sees_only_its_own_towns_and_the_route_needs_a_sign_in():
    h1, me1 = _org()
    h2, _ = _org()
    _insert(uuid.UUID(me1["org_id"]), [{"full_name": "Mine", "city": "Brest", **_full(9)}])
    assert "brest" in _asked(h1)
    assert _asked(h2) == {}
    assert requests.get(f"{API}/map/cities").status_code in (401, 403)
