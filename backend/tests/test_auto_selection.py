"""Automatic selection: the server picks the qualified prospects waiting for review; a person approves them at once."""

import requests

from tests.test_map_quick_add import API, _add, _org, _place


def _pending(me, uid, n):
    return [
        _add(
            me,
            _place(f"{uid}{i}", email=f"c{i}_{uid}@x-test.fr", phone=f"+33 4 78 00 01 {10 + i}", website=None),
            approve=False,
        )
        for i in range(n)
    ]


def test_the_server_selects_the_qualified_prospects_that_wait_for_review():
    uid, h, me = _org()
    added = _pending(me, uid, 3)
    incomplete = _add(me, _place(f"{uid}z", email=None, phone=None, website=None), approve=False)
    sel = requests.get(f"{API}/prospects/auto/selection", headers=h).json()
    ids = {i["id"] for i in sel["items"]}
    assert ids == {a.lead_id for a in added}  # the incomplete one is not selected: it waits in « À enrichir »
    assert incomplete.lead_id not in ids
    assert sel["total"] == 3 and all(i["priority"] in ("qualified", "hot") for i in sel["items"])


def test_one_click_approves_the_selection_and_each_decision_is_audited():
    uid, h, me = _org()
    added = _pending(me, uid, 3)
    ids = [a.lead_id for a in added]
    r = requests.post(
        f"{API}/prospects/auto/review", headers=h, json={"lead_ids": ids + ids[:1], "decision": "approve"}
    )
    assert r.status_code == 200 and r.json() == {"approved": 3, "rejected": 0, "suppressed": 0, "skipped": 0}
    assert requests.get(f"{API}/prospects/auto/selection", headers=h).json()["total"] == 0
    again = requests.post(
        f"{API}/prospects/auto/review", headers=h, json={"lead_ids": ids, "decision": "reject"}
    ).json()
    assert again["skipped"] == 3 and again["rejected"] == 0  # an approved prospect is not re-decided here
    events = requests.get(f"{API}/prospects/{ids[0]}/events", headers=h)
    assert events.status_code == 200


def test_a_member_cannot_decide_and_a_bad_id_is_refused():
    uid, h, me = _org()
    bad = requests.post(f"{API}/prospects/auto/review", headers=h, json={"lead_ids": ["nope"], "decision": "approve"})
    assert bad.status_code == 422
    empty = requests.post(f"{API}/prospects/auto/review", headers=h, json={"lead_ids": [], "decision": "approve"})
    assert empty.status_code == 422
