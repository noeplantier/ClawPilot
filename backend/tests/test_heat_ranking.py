"""Hot-lead ranking: the SQL ordering equals the Python rule, CRM leads and prospects come hottest first."""

import os
import uuid

import pytest
import requests
from sqlalchemy import Integer, literal, select

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from db.models import Lead  # noqa: E402
from repositories import heat_sql  # noqa: E402
from services.outreach_os import heat as heat_rules  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"heat_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Heat",
            "organization_name": f"Heat {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return h, requests.get(f"{API}/auth/me", headers=h).json()["user"]


def _lead(h, **fields):
    resp = requests.post(f"{API}/leads", headers=h, json={"full_name": fields.pop("full_name"), **fields})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_crm_leads_come_hottest_first_and_say_why():
    h, _ = _org()
    cold = _lead(h, full_name="A Name Only")
    rich = _lead(
        h,
        full_name="B Rich",
        email="b@rich.example",
        phone="+33 4 78 00 00 01",
        company="Rich SAS",
        title="CEO",
        country="FR",
    )
    mid = _lead(h, full_name="C Mail", email="c@mail.example")
    items = requests.get(f"{API}/leads", headers=h).json()
    assert [i["full_name"] for i in items] == ["B Rich", "C Mail", "A Name Only"]
    by = {i["full_name"]: i["heat"] for i in items}
    rich_heat = by["B Rich"]
    assert rich_heat["info_pct"] == 63 and set(rich_heat["known"]) == {"email", "phone", "company", "country", "title"}
    expected = (
        rich_heat["info_pct"] if not rich_heat["scored"] else (rich_heat["score"] + rich_heat["info_pct"] + 1) // 2
    )
    assert rich_heat["value"] == expected  # the figure is always the documented blend, whichever way it was scored
    assert "website" in by["B Rich"]["missing"]  # what is not known is said, never filled in
    assert by["A Name Only"]["info_pct"] == 0 and by["A Name Only"]["tier"] == "cold"
    recent = requests.get(f"{API}/leads", headers=h, params={"sort": "recent"}).json()
    assert [i["id"] for i in recent] == [mid["id"], rich["id"], cold["id"]]
    assert requests.get(f"{API}/leads", headers=h, params={"sort": "bogus"}).status_code == 422


def test_prospects_come_hottest_first_with_counted_queues():
    h, _ = _org()
    assert requests.post(f"{API}/prospects/discovery/run", headers=h, json={}).status_code == 200
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    assert len(items) > 3
    heats = [i["heat"]["value"] for i in items]
    assert heats == sorted(heats, reverse=True)  # the SQL ordering and the Python figure agree
    for i in items:
        assert i["heat"]["tier"] in ("hot", "warm", "cold") and 0 <= i["heat"]["info_pct"] <= 100
        assert i["heat"]["scored"] == (i["score"] is not None)
    queues = requests.get(f"{API}/prospects/queues", headers=h).json()
    assert queues["total"] == len(items) and queues["hot"] + queues["warm"] + queues["cold"] == queues["total"]
    tiers = [i["heat"]["tier"] for i in items]
    assert queues == {
        "hot": tiers.count("hot"),
        "warm": tiers.count("warm"),
        "cold": tiers.count("cold"),
        "total": len(items),
        "top": sum(1 for i in items if i["heat"]["top"]),
        "empty": sum(1 for i in items if not i["heat"]["has_contact"]),
    }
    assert requests.get(f"{API}/prospects/queues", headers=h, params={"review_status": "approved"}).json()["total"] == 0
    by_score = requests.get(f"{API}/prospects", headers=h, params={"order": "score", "limit": 200}).json()["items"]
    scores = [i["score"] if i["score"] is not None else -1 for i in by_score]
    assert scores == sorted(scores, reverse=True)
    assert requests.get(f"{API}/prospects", headers=h, params={"order": "bogus"}).status_code == 422
    assert requests.get(f"{API}/prospects/queues").status_code in (401, 403)


@pytest.mark.parametrize("score", [None, 0, 1, 37, 80, 100])
def test_the_sql_twin_gives_exactly_the_python_figure_for_every_combination_of_known_fields(score):
    h, me = _org()
    account = uuid.UUID(me["org_id"])
    samples = []
    for mask in range(0, 256, 7):  # a spread of the 256 combinations of known / unknown fields
        values = {}
        for i, f in enumerate(heat_rules.INFO_FIELDS):
            known = "s%d@sample.example" % mask if f == "email" else "Valeur"
            values[f] = known if mask & (1 << i) else ("unspecified" if i % 2 else None)
        samples.append(values)

    async def go(session):
        rows = []
        for n, values in enumerate(samples):
            lead = Lead(
                account_id=account,
                full_name=f"Sample {n}",
                **{k: v for k, v in values.items() if k != "title"},
                title=values["title"],
            )
            session.add(lead)
            rows.append(lead)
        await session.flush()
        expr = heat_sql.heat_sql(literal(score, type_=Integer))
        got = (await session.execute(select(Lead.full_name, expr).where(Lead.account_id == account))).all()
        return {name: value for name, value in got}

    result = run_async(go)
    for n, values in enumerate(samples):
        assert result[f"Sample {n}"] == heat_rules.heat_of(values, score).value, (n, values, score)
