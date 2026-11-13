"""The autopilot: off by default, turned on by an owner with four acknowledgements, a run that searches (faked
Overpass, no network), adds, approves and prepares, and never sends."""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests

from tasks import _bridge
from tests.test_map_quick_add import API, _add, _org, _place

ZONE = {"south": 45.75, "west": 4.82, "north": 45.77, "east": 4.86, "category": "bakeries"}
ACKS = ["b2b_use", "auto_approve", "ai_credits", "can_stop"]


def _run(account_id, fetcher=None, now=None):
    from services import autopilot_runner

    return asyncio.run(
        autopilot_runner.run(uuid.UUID(account_id), now, session_factory=_bridge._SessionLocal, fetcher=fetcher)
    )


def test_off_by_default_and_a_run_on_demand_is_refused():
    _, h, _ = _org()
    state = requests.get(f"{API}/autopilot", headers=h).json()
    assert state["enabled"] is False and state["acknowledgements"] == ACKS
    assert set(state["requirements"]) == {"external_sources", "prospect_import", "automation_max", "live_sending"}
    r = requests.post(f"{API}/autopilot/run", headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "autopilot_off"


def test_every_acknowledgement_is_required_and_the_owner_turns_it_on_and_off():
    _, h, _ = _org()
    bad = requests.put(f"{API}/autopilot", headers=h, json={"zone": ZONE, "acknowledgements": ACKS[:2]})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "acknowledgements_required"
    big = requests.put(f"{API}/autopilot", headers=h, json={"zone": {**ZONE, "north": 46.9}, "acknowledgements": ACKS})
    assert big.status_code == 422 and big.json()["detail"]["code"] == "zone_too_large"
    on = requests.put(f"{API}/autopilot", headers=h, json={"zone": ZONE, "acknowledgements": ACKS, "max_approvals": 20})
    assert on.status_code == 200 and on.json()["enabled"] is True and on.json()["max_approvals"] == 20
    off = requests.post(f"{API}/autopilot/disable", headers=h).json()
    assert off["enabled"] is False and off["zone"]["category"] == "bakeries"  # the settings are kept for next time


def test_a_run_approves_the_qualified_prospects_waiting_for_review_and_sends_nothing():
    uid, h, me = _org()
    for i in range(3):
        _add(
            me,
            _place(f"{uid}{i}", email=f"a{i}_{uid}@x-test.fr", phone=f"+33 4 78 00 02 {10 + i}", website=None),
            approve=False,
        )
    requests.put(f"{API}/autopilot", headers=h, json={"acknowledgements": ACKS, "max_approvals": 2}).raise_for_status()
    out = _run(me["org_id"])
    assert out["status"] == "ok" and "discovery" not in out  # no zone: nothing searched
    assert out["approval"]["approved"] == 2  # bounded by max_approvals
    crm = requests.get(f"{API}/leads", headers=h).json()
    assert sorted(lead["review_status"] for lead in crm) == ["approved", "approved", "pending"]
    assert requests.get(f"{API}/outbound", headers=h).json() == []  # nothing dispatched: the autopilot never sends
    assert requests.get(f"{API}/autopilot", headers=h).json()["last_run_at"]


def test_a_due_search_adds_the_reachable_places_then_waits_for_the_interval():
    uid, h, me = _org()
    shift = (
        int(uid[:4], 16) / 1e7
    )  # a zone of its own: the server's shared Overpass cache never answers from a previous run
    zone = {**ZONE, "south": ZONE["south"] + shift, "north": ZONE["north"] + shift}
    requests.put(f"{API}/autopilot", headers=h, json={"zone": zone, "acknowledgements": ACKS}).raise_for_status()
    answer = {
        "elements": [
            {
                "type": "node",
                "id": 9100 + i,
                "lat": 45.76,
                "lon": 4.84 + i / 1000,
                "tags": {
                    "name": f"Boulangerie {uid} {i}",
                    "shop": "bakery",
                    "phone": f"+33 4 78 00 03 {10 + i}",
                    "email": f"b{i}_{uid}@pain-test.fr",
                    "addr:street": "Rue Test",
                    "addr:housenumber": str(i + 1),
                    "addr:postcode": "69002",
                    "addr:city": "Lyon",
                },
            }
            for i in range(2)
        ]
        + [{"type": "node", "id": 9199, "lat": 45.76, "lon": 4.85, "tags": {"name": "Sans contact", "shop": "bakery"}}]
    }
    calls = []

    def fetcher(query):
        calls.append(query)
        return answer

    os.environ["FEATURE_EXTERNAL_SOURCES"] = "true"
    os.environ["FEATURE_PROSPECT_IMPORT"] = "true"
    try:
        now = datetime.now(timezone.utc)
        out = _run(me["org_id"], fetcher, now)
        assert out["discovery"]["search"] == "ok" and out["discovery"]["reachable"] == 2
        assert out["discovery"]["created"] == 2  # the place without a contact is never added
        again = _run(me["org_id"], fetcher, now + timedelta(hours=1))
        assert "discovery" not in again  # not searched again before the interval
        assert len(calls) == 1  # one Overpass request for the zone
    finally:
        del os.environ["FEATURE_EXTERNAL_SOURCES"]
        del os.environ["FEATURE_PROSPECT_IMPORT"]
    names = {lead["full_name"] for lead in requests.get(f"{API}/leads", headers=h).json()}
    assert names == {f"Boulangerie {uid} 0", f"Boulangerie {uid} 1"}


def test_without_the_external_sources_flag_the_search_is_skipped_and_said():
    _, h, me = _org()
    requests.put(f"{API}/autopilot", headers=h, json={"zone": ZONE, "acknowledgements": ACKS}).raise_for_status()
    out = _run(me["org_id"], lambda q: {"elements": []})
    assert out["discovery"]["search"] == "skipped" and "FEATURE_EXTERNAL_SOURCES" in out["discovery"]["why"]
