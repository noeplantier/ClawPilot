"""TOP leads and empty leads: the SQL rules equal the Python ones, lists and counts agree, and Leads ranks prospects on
their real score (a discovery prospect is scored in `prospect_scores`, not in `Lead.score`)."""

import os
import uuid

import pytest
import requests
from sqlalchemy import Integer, literal, select

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from db.models import Lead  # noqa: E402
from repositories import heat_sql, prospect_repo  # noqa: E402
from services.outreach_os import heat as heat_rules  # noqa: E402
from services.outreach_os.scoring import ScoreConfig, ScoreResult  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ALL = {
    "email": "{n}@top.example",
    "phone": "+33 4 78 00 00 01",
    "website": "https://top.example",
    "city": "Lyon",
    "company": "Top SAS",
    "vertical": "restaurants",
    "country": "FR",
    "title": "Owner",
}
# name -> (known fields, score or None)
PROSPECTS = {
    "Top Rich": (ALL, 90),  # (90 + 100 + 1) // 2 = 95: TOP
    "Hot Not Top": ({k: ALL[k] for k in ("email", "phone", "website", "city", "company")}, 75),  # 69: hot, below 80
    "Warm Mail": ({"email": "{n}@mail.example", "city": "Lyon"}, 60),  # (60 + 25 + 1) // 2 = 43
    "Empty Name": ({}, None),  # nothing known, never scored: empty
    "Empty But Scored": (
        {"city": "Lyon", "company": "No Way In"},
        90,
    ),  # 58 and warm, but still nothing to reach it with
    "Site Only": ({"website": "https://site-only.example"}, None),  # 13: cold, yet reachable
}
EMPTY = {"Empty Name", "Empty But Scored"}


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"top_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Top",
            "organization_name": f"Top {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return h, requests.get(f"{API}/auth/me", headers=h).json()["user"]


def _seed(me):
    account = uuid.UUID(me["org_id"])

    async def go(session):
        version = await prospect_repo.create_score_version(session, account, ScoreConfig(), None)
        for n, (name, (fields, score)) in enumerate(PROSPECTS.items()):
            values = {k: v.format(n=n) for k, v in fields.items()}
            lead = Lead(account_id=account, full_name=name, review_status="pending", **values)
            session.add(lead)
            await session.flush()
            if score is not None:
                result = ScoreResult(score=score, coverage=1.0, lines=[], config_hash=version.config_hash)
                await prospect_repo.append_score(session, account, lead.id, version, result)

    run_async(go)


def _get(h, path, **params):
    resp = requests.get(f"{API}{path}", headers=h, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_prospects_say_which_are_top_and_which_are_empty_and_hide_the_empty_on_request():
    h, me = _org()
    _seed(me)
    everyone = _get(h, "/prospects", limit=200)
    by_name = {i["name"]: i for i in everyone["items"]}
    assert set(by_name) == set(PROSPECTS) and everyone["total"] == 6  # nothing is hidden unless asked
    assert {n for n, i in by_name.items() if i["heat"]["top"]} == {"Top Rich"}
    assert {n for n, i in by_name.items() if not i["heat"]["has_contact"]} == EMPTY
    assert by_name["Top Rich"]["heat"]["value"] == 95 and by_name["Hot Not Top"]["heat"]["tier"] == "hot"
    assert by_name["Empty But Scored"]["heat"]["tier"] == "warm"  # a good score does not make an empty lead reachable
    assert [i["name"] for i in everyone["items"]][0] == "Top Rich"  # the TOP lead comes first

    reachable = _get(h, "/prospects", limit=200, hide_empty="true")
    assert reachable["total"] == 4
    assert {i["name"] for i in reachable["items"]} == set(PROSPECTS) - EMPTY
    assert all(i["heat"]["has_contact"] for i in reachable["items"])
    paged = _get(h, "/prospects", limit=1, offset=3, hide_empty="true")
    assert paged["total"] == 4 and len(paged["items"]) == 1  # the total follows the filter, so paging is right


def test_the_queue_counts_say_how_many_are_top_and_how_many_are_empty():
    h, me = _org()
    _seed(me)
    shown = _get(h, "/prospects/queues", review_status="pending")
    assert shown == {"hot": 2, "warm": 2, "cold": 2, "total": 6, "top": 1, "empty": 2}
    hidden = _get(h, "/prospects/queues", review_status="pending", hide_empty="true")
    assert hidden == {"hot": 2, "warm": 1, "cold": 1, "total": 4, "top": 1, "empty": 2}
    assert _get(h, "/prospects/queues", review_status="approved") == {
        "hot": 0, "warm": 0, "cold": 0, "total": 0, "top": 0, "empty": 0,
    }  # fmt: skip


def test_leads_rank_a_prospect_on_its_real_score_and_agree_with_the_prospects_page():
    h, me = _org()
    _seed(me)
    for body in ({"full_name": "CRM Empty"}, {"full_name": "CRM Mail", "email": "crm@mail.example"}):
        assert requests.post(f"{API}/leads", headers=h, json=body).status_code == 200
    leads = {i["full_name"]: i for i in _get(h, "/leads")}
    prospects = {i["name"]: i for i in _get(h, "/prospects", limit=200)["items"]}
    for name, p in prospects.items():
        lead = leads[name]
        assert lead["heat"] == p["heat"], name  # one lead, one heat, whichever page shows it
        assert lead["score"] == p["score"] if p["score"] is not None else lead["score"] == 0
    assert leads["CRM Empty"]["heat"]["has_contact"] is False and leads["CRM Mail"]["heat"]["has_contact"] is True
    ordered = [i["heat"]["value"] for i in _get(h, "/leads")]
    assert ordered == sorted(ordered, reverse=True)  # hottest first, prospects included
    assert _get(h, "/leads")[0]["full_name"] == "Top Rich" and _get(h, "/leads")[0]["heat"]["top"] is True


@pytest.mark.parametrize("score", [None, 0, 37, 59, 60, 80, 100])
def test_the_sql_twin_gives_exactly_the_python_top_and_empty_flags(score):
    h, me = _org()
    account = uuid.UUID(me["org_id"])
    samples = []
    for mask in range(0, 256, 5):  # a spread of the 256 combinations of known / unknown fields
        samples.append(
            {
                f: (
                    (f"v{mask}@x.example" if f == "email" else "Valeur")
                    if mask & (1 << i)
                    else ("unspecified" if i % 2 else None)
                )
                for i, f in enumerate(heat_rules.INFO_FIELDS)
            }
        )

    async def go(session):
        for n, values in enumerate(samples):
            session.add(Lead(account_id=account, full_name=f"Sample {n}", **values))
        await session.flush()
        heat = heat_sql.heat_sql(literal(score, type_=Integer))
        rows = await session.execute(
            select(Lead.full_name, heat_sql.has_contact_sql(), heat_sql.top_sql(heat)).where(Lead.account_id == account)
        )
        return {name: (bool(c), bool(t)) for name, c, t in rows.all()}

    got = run_async(go)
    for n, values in enumerate(samples):
        expected = heat_rules.heat_of(values, score)
        assert got[f"Sample {n}"] == (expected.has_contact, expected.top), (n, values, score)
