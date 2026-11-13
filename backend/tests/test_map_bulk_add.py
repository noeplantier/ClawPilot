"""One click on the map's selection: every place joins the CRM through the same attested import as the single click.

Called in-process with the import flag set (the test server keeps it off, like production defaults); the results are
read back over HTTP. No network: websites are not fetched (`check_website=False`).
"""

import os
import uuid

import pytest
import requests
from fastapi import HTTPException

from tests.test_map_quick_add import API, _add, _org, _place


def _add_many(me, places, **opts):
    from models import MapAddManyIn
    from routes import map_search
    from tasks._bridge import run_async

    payload = MapAddManyIn(places=places, attestation=opts.pop("attestation", True), check_website=False, **opts)
    os.environ["FEATURE_PROSPECT_IMPORT"] = "true"
    try:

        async def go(session):
            return await map_search.add_places(payload, user=me, session=session)

        return run_async(go)
    finally:
        del os.environ["FEATURE_PROSPECT_IMPORT"]


def _three(uid):
    return [
        _place(f"{uid}a", email=f"a_{uid}@a-test.fr", phone="+33 4 78 00 00 11", website=None),
        _place(f"{uid}b", email=f"b_{uid}@b-test.fr", phone="+33 4 78 00 00 12", website=None),
        _place(f"{uid}c", email=None, phone="+33 4 78 00 00 13", website=None),
    ]


def test_one_click_puts_the_whole_selection_in_the_crm():
    uid, h, me = _org()
    out = _add_many(me, _three(uid))
    assert (out.requested, out.created, out.in_crm, out.waiting_review) == (3, 3, 3, 0)
    assert out.suppressed == 0 and out.kept_rejected == 0 and len(out.lead_ids) == 3
    crm = requests.get(f"{API}/leads", headers=h).json()
    assert sorted(lead["review_status"] for lead in crm) == ["approved"] * 3


def test_a_second_click_duplicates_nothing():
    uid, h, me = _org()
    _add_many(me, _three(uid))
    again = _add_many(me, _three(uid))
    assert again.created == 0 and again.already_known == 3 and again.in_crm == 3
    assert len(requests.get(f"{API}/leads", headers=h).json()) == 3


def test_a_rejected_prospect_stays_rejected():
    uid, h, me = _org()
    places = _three(uid)
    first = _add(me, places[0], approve=False)
    requests.post(f"{API}/prospects/{first.lead_id}/review", headers=h, json={"decision": "reject"}).raise_for_status()
    out = _add_many(me, places)
    assert out.kept_rejected == 1 and out.in_crm == 2
    assert requests.get(f"{API}/prospects/{first.lead_id}", headers=h).json()["review_status"] == "rejected"


def test_without_approval_the_selection_waits_for_review():
    uid, h, me = _org()
    out = _add_many(me, _three(uid), approve=False)
    assert out.in_crm == 0 and out.waiting_review == 3


def test_the_attestation_is_required_and_nothing_is_written_without_it():
    uid, h, me = _org()
    with pytest.raises(HTTPException) as refused:
        _add_many(me, _three(uid), attestation=False)
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "attestation_required"
    assert requests.get(f"{API}/leads", headers=h).json() == []


def test_the_flag_is_required():
    from models import MapAddManyIn
    from routes import map_search
    from tasks._bridge import run_async

    uid, h, me = _org()
    payload = MapAddManyIn(places=_three(uid), attestation=True, check_website=False)

    async def go(session):
        return await map_search.add_places(payload, user=me, session=session)

    with pytest.raises(HTTPException) as refused:
        run_async(go)
    assert refused.value.status_code == 403
    assert uuid.UUID(me["org_id"])  # the account exists, nothing was added
    assert requests.get(f"{API}/leads", headers=h).json() == []
