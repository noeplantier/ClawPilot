"""GET /suggestions/focus: where to prospect next and who to contact first, counted from the stored leads.

Rows are written in-process (a CRM lead cannot carry a city through POST /leads) and read back over HTTP; the answer is
compared with what the rows say, so nothing in it is estimated."""

import os
import uuid

import requests

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from prospect_fixtures import insert_rows, row  # noqa: E402

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


def test_the_best_zones_and_leads_are_the_qualified_ones_and_only_those():
    h, me, uid = _org()
    account = uuid.UUID(me["org_id"])
    suppressed = row("Supprimé", "Rennes", website="https://supprime.fr")
    insert_rows(
        account,
        [
            row("Lyon A", "Lyon", website="https://lyon-a.fr"),
            row("Lyon B", "Lyon", website="https://lyon-b.fr"),
            row("Lyon C", "lyon ", website="https://lyon-c.fr"),
            row("Lyon sans site", "Lyon"),
            row("Rennes A", "Rennes", website="https://rennes-a.fr"),
            row("Rennes B", "Rennes", website="https://rennes-b.fr"),
            row("Rennes rejeté", "Rennes", review_status="rejected", website="https://rennes-r.fr"),
            row("Brest sans tel", "Brest", phone=None),
            row("Brest sans adresse", "Brest", address=None),
            suppressed,
        ],
        suppress_emails=[suppressed["lead"]["email"]],
    )
    out = requests.get(f"{API}/suggestions/focus", headers=h)
    assert out.status_code == 200, out.text
    body = out.json()

    zones = {z["key"]: z for z in body["zones"]}
    assert [z["key"] for z in body["zones"]][:2] == ["lyon", "rennes"]  # most qualified prospects first
    assert (zones["lyon"]["ready"], zones["lyon"]["site"]) == (4, 3)  # the one without a website counts as well
    assert zones["rennes"]["ready"] == 2  # the suppressed prospect is no longer counted ready while never suggested
    assert "brest" not in zones  # a town where nobody has both a phone and an address is not suggested

    names = [lead["name"] for lead in body["leads"]]
    assert set(names[:5]) == {"Lyon A", "Lyon B", "Lyon C", "Rennes A", "Rennes B"}
    assert names[5] == "Lyon sans site" and len(names) == 6  # a lower heat (no website), still suggested; nobody else
    assert not {"Supprimé", "Rennes rejeté", "Brest sans tel", "Brest sans adresse"} & set(names)
    for lead in body["leads"]:
        assert lead["phone"] and lead["email"] and lead["kind"] == "prospect" and lead["priority"] == "qualified"
    assert next(x for x in body["leads"] if x["name"] == "Lyon sans site")["website"] is None  # unknown stays unknown


def test_the_limits_are_honoured_and_an_organisation_with_nothing_ready_gets_empty_lists():
    h, me, uid = _org()
    account = uuid.UUID(me["org_id"])
    assert requests.get(f"{API}/suggestions/focus", headers=h).json()["zones"] == []
    insert_rows(account, [row(f"L{n}", f"Ville{n}", website=f"https://l{n}.fr") for n in range(1, 5)])
    out = requests.get(f"{API}/suggestions/focus", headers=h, params={"zones": 2, "leads": 3}).json()
    assert (len(out["zones"]), len(out["leads"])) == (2, 3)
    assert requests.get(f"{API}/suggestions/focus", headers=h, params={"zones": 0}).status_code == 422


def test_each_organisation_sees_only_its_own_suggestions_and_the_route_needs_a_sign_in():
    h1, me1, uid1 = _org()
    h2, _, _ = _org()
    insert_rows(uuid.UUID(me1["org_id"]), [row("Mine", "Brest", website="https://mine.fr")])
    assert requests.get(f"{API}/suggestions/focus", headers=h1).json()["leads"][0]["name"] == "Mine"
    assert requests.get(f"{API}/suggestions/focus", headers=h2).json()["leads"] == []
    assert requests.get(f"{API}/suggestions/focus").status_code in (401, 403)
