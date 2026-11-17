"""The CRM list is capped; its count is not. An approved prospect can always be found (filter + count), per account."""

import requests

from tests.test_map_quick_add import API, _add, _org, _place


def _three_pending(me, uid):
    return [
        _add(
            me,
            _place(f"{uid}{i}", email=f"c{i}_{uid}@crm-test.fr", phone=f"+33 4 78 00 05 {10 + i}", website=None),
            approve=False,
        )
        for i in range(3)
    ]


def test_an_approved_prospect_is_found_with_the_filter_and_counted():
    uid, h, me = _org()
    added = _three_pending(me, uid)
    requests.post(
        f"{API}/prospects/{added[0].lead_id}/review", headers=h, json={"decision": "approve"}
    ).raise_for_status()
    approved = requests.get(f"{API}/leads", headers=h, params={"review_status": "approved"}).json()
    assert [lead["id"] for lead in approved] == [added[0].lead_id]
    assert approved[0]["email"] and approved[0]["phone"] and approved[0]["city"] == "Lyon"  # the useful fields are kept
    assert requests.get(f"{API}/leads/count", headers=h, params={"review_status": "approved"}).json() == {"total": 1}
    assert requests.get(f"{API}/leads/count", headers=h).json() == {"total": 3}


def test_a_cut_list_is_never_silent():
    uid, h, me = _org()
    _three_pending(me, uid)
    cut = requests.get(f"{API}/leads", headers=h, params={"limit": 2}).json()
    assert len(cut) == 2 and requests.get(f"{API}/leads/count", headers=h).json()["total"] == 3


def test_counts_and_filters_stay_inside_the_account():
    uid, h, me = _org()
    _three_pending(me, uid)
    _, other, _ = _org()
    assert requests.get(f"{API}/leads/count", headers=other).json() == {"total": 0}
    assert requests.get(f"{API}/leads", headers=other, params={"review_status": "pending"}).json() == []


def test_an_unknown_review_status_is_refused():
    _, h, _ = _org()
    assert requests.get(f"{API}/leads", headers=h, params={"review_status": "maybe"}).status_code == 422
    assert requests.get(f"{API}/leads/count", headers=h, params={"review_status": "maybe"}).status_code == 422
