"""GET /suggestions/focus: where to prospect next and who to contact first, counted from the stored leads.

Rows are written in-process (a CRM lead cannot carry a city through POST /leads) and read back over HTTP; the answer is
compared with what the rows say, so nothing in it is estimated."""

import os
import uuid

import requests

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from db.models import Lead  # noqa: E402
from repositories import suppression_repo  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"focus_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Focus",
            "organization_name": f"Focus {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return h, requests.get(f"{API}/auth/me", headers=h).json()["user"], uid


def _full(n, uid, **over):  # all eight tracked fields known: heat 100, hot, phone and e-mail present
    base = {
        "email": f"{n}.{uid}@full.example",
        "phone": f"+33 4 78 00 00 {n:02d}",
        "website": f"https://full{n}.example",
        "company": f"Full {n} SAS",
        "vertical": "restaurants",
        "country": "FR",
        "title": "Owner",
    }
    return {**base, **over}


def _insert(account, rows, suppress=()):
    async def go(session):
        for r in rows:
            session.add(Lead(account_id=account, **r))
        await session.flush()
        for email in suppress:
            await suppression_repo.add(session, account, "email", email, reason="opt_out")

    run_async(go)


def test_the_best_zones_and_leads_are_the_hot_reachable_ones_and_only_those():
    h, me, uid = _org()
    account = uuid.UUID(me["org_id"])
    _insert(
        account,
        [
            {"full_name": "Lyon A", "city": "Lyon", **_full(1, uid)},
            {"full_name": "Lyon B", "city": "Lyon", **_full(2, uid)},
            {"full_name": "Lyon C", "city": "lyon ", **_full(3, uid)},
            {"full_name": "Lyon sans site", "city": "Lyon", **_full(4, uid, website=None)},
            {"full_name": "Rennes A", "city": "Rennes", **_full(5, uid)},
            {"full_name": "Rennes B", "city": "Rennes", **_full(6, uid)},
            {"full_name": "Rennes rejeté", "city": "Rennes", "review_status": "rejected", **_full(7, uid)},
            {"full_name": "Brest mail seul", "city": "Brest", "email": f"b.{uid}@brest.example", "company": "B"},
            {"full_name": "Brest tel seul", "city": "Brest", "phone": "+33 2 98 00 00 01", "company": "B2"},
            {"full_name": "Supprimé", "city": "Rennes", **_full(8, uid)},
        ],
        suppress=[f"8.{uid}@full.example"],
    )
    out = requests.get(f"{API}/suggestions/focus", headers=h)
    assert out.status_code == 200, out.text
    body = out.json()

    zones = {z["key"]: z for z in body["zones"]}
    assert [z["key"] for z in body["zones"]][:2] == ["lyon", "rennes"]  # most ready hot leads first
    assert (zones["lyon"]["ready"], zones["lyon"]["site"], zones["lyon"]["hot"]) == (4, 3, 4)
    assert "brest" not in zones  # a town with hot-or-not leads nobody can both call and e-mail is not suggested
    # a suppressed lead still counts in its town's figures (they describe the data) but is never suggested to contact

    names = [lead["name"] for lead in body["leads"]]
    assert set(names[:5]) == {"Lyon A", "Lyon B", "Lyon C", "Rennes A", "Rennes B"}  # a website ranks a lead first ...
    assert names[5] == "Lyon sans site" and len(names) == 6  # ... then the one without; nobody else qualifies
    assert not {"Supprimé", "Rennes rejeté", "Brest mail seul", "Brest tel seul"} & set(names)
    for lead in body["leads"]:
        assert lead["phone"] and lead["email"] and lead["heat"]["tier"] == "hot" and lead["kind"] == "lead"
    assert next(x for x in body["leads"] if x["name"] == "Lyon sans site")["website"] is None  # unknown stays unknown


def test_the_limits_are_honoured_and_an_organisation_with_nothing_ready_gets_empty_lists():
    h, me, uid = _org()
    account = uuid.UUID(me["org_id"])
    assert requests.get(f"{API}/suggestions/focus", headers=h).json()["zones"] == []
    _insert(account, [{"full_name": f"L{n}", "city": f"Ville{n}", **_full(n, uid)} for n in range(1, 5)])
    out = requests.get(f"{API}/suggestions/focus", headers=h, params={"zones": 2, "leads": 3}).json()
    assert (len(out["zones"]), len(out["leads"])) == (2, 3)
    assert requests.get(f"{API}/suggestions/focus", headers=h, params={"zones": 0}).status_code == 422


def test_each_organisation_sees_only_its_own_suggestions_and_the_route_needs_a_sign_in():
    h1, me1, uid1 = _org()
    h2, _, _ = _org()
    _insert(uuid.UUID(me1["org_id"]), [{"full_name": "Mine", "city": "Brest", **_full(9, uid1)}])
    assert requests.get(f"{API}/suggestions/focus", headers=h1).json()["leads"][0]["name"] == "Mine"
    assert requests.get(f"{API}/suggestions/focus", headers=h2).json()["leads"] == []
    assert requests.get(f"{API}/suggestions/focus").status_code in (401, 403)
