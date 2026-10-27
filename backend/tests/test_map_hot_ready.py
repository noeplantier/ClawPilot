"""GET /map/prospects: the map shows hot leads that can be called AND e-mailed; a website only ranks them higher.

Rows are imported through the real importer (flag set in-process, no network); the readiness the server answers with is
compared with the Python heat rule applied to the same answer, so the two can never disagree."""

import json
import os
import uuid

import requests

from services.outreach_os import heat as heat_rules

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _score(account, names, value):
    """Append a newer explainable score to the named prospects (an import alone scores low: nothing is detected yet)."""
    from sqlalchemy import select

    from db.models import Lead, ProspectScore
    from tasks._bridge import run_async

    async def go(session):
        leads = (await session.execute(select(Lead).where(Lead.account_id == account))).scalars().all()
        for lead in leads:
            if lead.full_name.rsplit(" ", 1)[0] in names:
                last = (
                    (
                        await session.execute(
                            select(ProspectScore)
                            .where(ProspectScore.lead_id == lead.id)
                            .order_by(ProspectScore.created_at.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
                session.add(
                    ProspectScore(
                        account_id=account,
                        lead_id=lead.id,
                        score_version_id=last.score_version_id,
                        score=value,
                        coverage=1.0,
                        breakdown=[],
                    )
                )
        await session.flush()

    run_async(go)


def _seed(rows):
    from models import ImportIn
    from routes import prospect_imports
    from tasks._bridge import run_async

    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"hr_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "H",
            "organization_name": f"H {uid}",
        },
    ).json()
    h = {"Authorization": f"Bearer {reg['access_token']}"}
    me = requests.get(f"{API}/auth/me", headers=h).json()["user"]
    os.environ["FEATURE_PROSPECT_IMPORT"] = "true"
    try:
        payload = ImportIn(
            format="json",
            content=json.dumps(rows(uid)),
            origin="A list typed by hand for this test",
            legal_basis="legitimate_interest_b2b",
            country="FR",
            vertical="restaurants",
            preview=False,
            attestation=True,
        )

        async def go(session):
            return await prospect_imports.import_prospects(payload, user=me, session=session)

        run_async(go)
    finally:
        del os.environ["FEATURE_PROSPECT_IMPORT"]
    return uid, h, uuid.UUID(me["org_id"])


def test_the_server_marks_only_hot_reachable_leads_and_ranks_the_website_first():
    def rows(uid):
        base = lambda name, n, **extra: {  # noqa: E731
            "name": name,
            "lat": 45.76 + n / 1000,
            "lon": 4.83,
            "external_id": f"node/{uid}{n}",
            "city": "Lyon",
            **extra,
        }
        return [
            base(
                f"Complet {uid}",
                1,
                email=f"a_{uid}@full.example",
                phone="+33 4 78 00 00 01",
                website="https://full.example",
            ),
            base(f"Sans site {uid}", 2, email=f"b_{uid}@nosite.example", phone="+33 4 78 00 00 02"),
            base(f"Mail seul {uid}", 3, email=f"c_{uid}@mail.example"),
            base(f"Tel seul {uid}", 4, phone="+33 4 78 00 00 04"),
            base(f"Rien {uid}", 5),
        ]

    uid, h, account = _seed(rows)
    _score(account, {"Complet", "Sans site", "Mail seul", "Tel seul", "Rien"}, 90)
    items = requests.get(f"{API}/map/prospects", headers=h).json()
    by_name = {p["name"].rsplit(" ", 1)[0]: p for p in items}
    assert set(by_name) == {"Complet", "Sans site", "Mail seul", "Tel seul", "Rien"}

    for p in items:  # the answer agrees with the Python rule, field by field
        assert p["has_phone"] == bool(p["phone"]) and p["has_website"] == bool(p["website"])
        assert p["map_ready"] == (p["heat"]["tier"] == "hot" and bool(p["phone"]) and bool(p["email"]))
    assert by_name["Complet"]["map_ready"] is True and by_name["Sans site"]["map_ready"] is True  # hot, phone + e-mail
    assert (
        by_name["Mail seul"]["map_ready"] is False and by_name["Mail seul"]["phone"] is None
    )  # no phone: never on the map
    assert (
        by_name["Tel seul"]["map_ready"] is False and by_name["Tel seul"]["email"] is None
    )  # no e-mail: never on the map
    assert by_name["Rien"]["map_ready"] is False
    assert by_name["Complet"]["website"] == "https://full.example" and by_name["Complet"]["phone"]
    assert by_name["Sans site"]["website"] is None  # a missing website stays unknown: not filled in, not faked

    ready = [p for p in items if p["map_ready"]]
    assert [p["has_website"] for p in ready] == sorted((p["has_website"] for p in ready), reverse=True)  # website first
    assert [p["map_ready"] for p in items] == sorted((p["map_ready"] for p in items), reverse=True)  # ready ones lead


def test_a_not_ready_lead_stays_in_the_answer_so_the_search_does_not_offer_the_place_again():
    def rows(uid):
        return [{"name": f"Tiede {uid}", "lat": 45.7, "lon": 4.8, "external_id": f"node/t{uid}", "city": "Lyon"}]

    _, h, _ = _seed(rows)
    items = requests.get(f"{API}/map/prospects", headers=h).json()
    assert len(items) == 1 and items[0]["map_ready"] is False and items[0]["external_id"].startswith("node/t")
    assert heat_rules.HOT_FROM == 65
