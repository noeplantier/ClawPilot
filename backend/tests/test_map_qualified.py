"""GET /map/prospects: the commercial map draws the prospects the common eligibility policy qualifies — and only those.

Qualified = e-mail, phone, address and position on a fresh source, a fit score. A website or WhatsApp is never required,
a missing part keeps the prospect in the "to enrich" queue, and nothing here invents a purchase intent: "hot" stays
empty until a sourced `commercial_intent` signal exists. Rows are written in-process, read back over HTTP."""

import os
import uuid

import requests
from prospect_fixtures import insert_rows, row

from db.models import ProspectSignal, ProspectSource
from tasks._bridge import run_async

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"mq_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Map",
            "organization_name": f"Map {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return h, uuid.UUID(requests.get(f"{API}/auth/me", headers=h).json()["user"]["org_id"])


def _map(h):
    resp = requests.get(f"{API}/map/prospects", headers=h)
    assert resp.status_code == 200, resp.text
    return {p["name"]: p for p in resp.json()}


def _queue(h):
    resp = requests.get(f"{API}/prospects/to-enrich", headers=h, params={"limit": 200})
    assert resp.status_code == 200, resp.text
    return {i["name"]: i for i in resp.json()["items"]}, resp.json()["total"]


def test_a_complete_prospect_is_drawn_with_or_without_a_website_and_without_any_whatsapp_proof():
    h, account = _org()
    insert_rows(
        account,
        [row("Avec site", website="https://avec-site.fr"), row("Sans site"), row("Fixe", phone="04 78 12 34 56")],
    )
    drawn = _map(h)
    assert set(drawn) == {"Avec site", "Sans site", "Fixe"}  # the site state excludes nobody
    assert drawn["Sans site"]["website"] is None and drawn["Sans site"]["has_website"] is False  # unknown stays unknown
    for p in drawn.values():
        assert p["eligible"] is True and p["map_ready"] is True and p["phone"] and p["email"] and p["address"]
        assert p["priority"] == "qualified" and p["priority_label"] == "Qualifié prioritaire"  # no intent: never Hot
        assert p["fit_score"] >= 60 and -90 <= p["lat"] <= 90


def test_a_missing_email_phone_address_or_position_keeps_the_prospect_off_the_map_and_in_the_queue():
    h, account = _org()
    insert_rows(
        account,
        [
            row("Ok"),
            row("Sans mail", email=None),
            row("Sans tel", phone=None),
            row("Sans adresse", address=None),
            row("Sans position", lat=None, lon=None),
            row("Mail bidon", email="x@example.com"),
            row("Sans source", source_days=None),
            row("Source ancienne", source_days=90),
            row("Non scoré", fit=None),
            row("Fit faible", fit=30),
        ],
    )
    assert set(_map(h)) == {"Ok"}
    queue, total = _queue(h)
    assert total == 9 and "Ok" not in queue  # nothing disappears: all nine wait to be enriched
    assert queue["Sans mail"]["missing_fields"] == ["email_missing"]
    assert queue["Sans tel"]["missing_fields"] == ["phone_missing"]
    assert queue["Sans adresse"]["missing_fields"] == ["address_missing"]
    assert queue["Sans position"]["missing_fields"] == ["coordinates_missing"]
    assert queue["Mail bidon"]["missing_fields"] == ["email_invalid"]
    assert "source_missing" in queue["Sans source"]["missing_fields"]
    assert queue["Source ancienne"]["missing_fields"] == ["source_stale"]
    assert queue["Non scoré"]["missing_fields"] == ["fit_missing"] and queue["Fit faible"]["missing_fields"] == [
        "fit_low"
    ]
    assert queue["Sans mail"]["email"] is None  # an unknown is shown as unknown, never filled in


def test_suppressed_rejected_and_demo_records_are_not_drawn_and_not_queued():
    h, account = _org()
    blocked = row("Bloqué")
    insert_rows(
        account,
        [
            row("Ok"),
            blocked,
            row("Rejeté", review_status="rejected"),
            row("Démo", source_name="fixture_directory"),
        ],
        suppress_emails=[blocked["lead"]["email"]],
    )
    assert set(_map(h)) == {"Ok"}
    queue, total = _queue(h)
    assert total == 0 and queue == {}  # excluded is not "to enrich": it must never be worked as a candidate


def test_hot_needs_an_observed_sourced_intent_and_never_comes_from_a_need_signal():
    h, account = _org()
    ids = insert_rows(account, [row("Calme"), row("Intéressé"), row("Besoin")])
    lead = {name: ids[i] for i, name in enumerate(["Calme", "Intéressé", "Besoin"])}

    async def signals(session):
        from sqlalchemy import select

        for name, key in (("Intéressé", "commercial_intent"), ("Besoin", "no_website")):
            source = (
                await session.execute(select(ProspectSource.id).where(ProspectSource.lead_id == uuid.UUID(lead[name])))
            ).scalar_one()
            session.add(
                ProspectSignal(
                    account_id=account,
                    lead_id=uuid.UUID(lead[name]),
                    source_id=source,
                    signal_key=key,
                    state="detected",
                    evidence="Asked for a quote on the contact page of the business's own site",
                )
            )

    run_async(signals)
    drawn = _map(h)
    assert drawn["Intéressé"]["priority"] == "hot" and drawn["Intéressé"]["priority_label"].startswith("Hot")
    assert drawn["Calme"]["priority"] == "qualified" and drawn["Besoin"]["priority"] == "qualified"
    assert [p["name"] for p in requests.get(f"{API}/map/prospects", headers=h).json()][0] == "Intéressé"  # hot first


def test_a_known_but_incomplete_place_is_still_known_so_the_search_does_not_offer_it_again():
    h, account = _org()
    insert_rows(account, [row("Complet"), row("Incomplet", phone=None)])
    known = requests.get(f"{API}/map/known", headers=h)
    assert known.status_code == 200, known.text
    assert len(known.json()) == 2  # both external ids, drawn or not


def test_each_organisation_sees_only_its_own_prospects_and_the_route_needs_a_sign_in():
    h1, a1 = _org()
    h2, _ = _org()
    insert_rows(a1, [row("Mine")])
    assert set(_map(h1)) == {"Mine"} and _map(h2) == {}
    assert requests.get(f"{API}/map/prospects").status_code in (401, 403)
    assert requests.get(f"{API}/prospects/to-enrich").status_code in (401, 403)


def test_the_answer_has_an_etag_and_an_unchanged_poll_costs_an_empty_304():
    h, account = _org()
    insert_rows(account, [row("Stable")])
    first = requests.get(f"{API}/map/prospects", headers=h)
    etag = first.headers["ETag"]
    again = requests.get(f"{API}/map/prospects", headers={**h, "If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    insert_rows(account, [row("Nouveau")])  # a new qualified prospect changes the tag at once
    changed = requests.get(f"{API}/map/prospects", headers={**h, "If-None-Match": etag})
    assert changed.status_code == 200 and {p["name"] for p in changed.json()} == {"Stable", "Nouveau"}
