"""Campaign suggestions from real data: counted, hottest first, gated by the same send rules, nothing sent."""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"sg_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Suggest",
            "organization_name": f"Suggest {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _suggestions(h):
    r = requests.get(f"{API}/campaigns/suggestions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _lead(h, name, **fields):
    r = requests.post(f"{API}/leads", headers=h, json={"full_name": name, **fields})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_new_organisation_gets_an_explicit_empty_list_not_invented_ideas():
    body = _suggestions(_org())
    assert body["items"] == [] and body["basis"] == {"prospects": 0, "leads": 0} and body["dry_run"] is True


def test_discovery_prospects_make_counted_suggestions_that_say_what_blocks_a_campaign():
    h = _org()
    assert requests.post(f"{API}/prospects/discovery/run", headers=h, json={}).status_code == 200
    body = _suggestions(h)
    assert body["basis"]["prospects"] > 3 and body["items"]
    prios = [i["priority"] for i in body["items"]]
    assert prios == sorted(prios, reverse=True)  # the most promising first
    for i in body["items"]:
        assert i["total"] >= 2 and i["rationale"] and i["examples"]
        assert i["hot"] <= i["total"] and i["with_email"] <= i["total"] and 0 <= i["avg_heat"] <= 100
        assert i["eligible"] == 0 and i["blocked_reason"]  # dry-run: discovery prospects cannot join a campaign yet
    first = body["items"][0]
    refused = requests.post(f"{API}/campaigns/suggestions/{first['id']}/create", headers=h)
    assert refused.status_code == 409 and "dry-run" in refused.json()["detail"]  # nothing to put in a campaign
    assert requests.get(f"{API}/campaigns", headers=h).json() == []  # and no empty campaign was left behind


def test_new_crm_leads_with_a_contact_become_a_suggestion_that_creates_a_draft_and_sends_nothing():
    h = _org()
    a = _lead(h, "Alice New", email="alice@new.example", company="Alice SAS")
    b = _lead(h, "Bob New", phone="+33 4 78 00 00 03", company="Bob SAS")
    _lead(h, "Carl Nobody")  # no contact: not part of the group
    body = _suggestions(h)
    group = next(i for i in body["items"] if i["kind"] == "new_leads")
    assert group["total"] == 2 and group["eligible"] == 2 and group["blocked_reason"] is None
    assert set(group["examples"]) == {"Alice SAS", "Bob SAS"}

    done = requests.post(f"{API}/campaigns/suggestions/{group['id']}/create", headers=h)
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["assigned"] == 2 and out["left_out"] == 0 and "nothing is sent" in out["note"]
    campaign = requests.get(f"{API}/campaigns/{out['campaign_id']}", headers=h).json()
    assert campaign["status"] == "draft" and campaign["steps"] == [] and campaign["sent"] == 0
    assert set(campaign["lead_ids"]) == {a["id"], b["id"]}
    assert group["rationale"] in campaign["goal"]
    audit = requests.get(f"{API}/dashboard/overview", headers=h)  # the page of the organisation still works
    assert audit.status_code == 200


def test_unknown_suggestion_is_404_a_rate_limit_applies_and_login_is_required():
    h = _org()
    assert requests.post(f"{API}/campaigns/suggestions/nope/create", headers=h).status_code == 404
    assert requests.get(f"{API}/campaigns/suggestions").status_code in (401, 403)
    assert requests.post(f"{API}/campaigns/suggestions/x/create").status_code in (401, 403)
    codes = [requests.post(f"{API}/campaigns/suggestions/nope{i}/create", headers=h).status_code for i in range(12)]
    assert 429 in codes


def test_organisations_never_see_each_others_suggestions():
    a, b = _org(), _org()
    _lead(a, "Only A 1", email="a1@only.example")
    _lead(a, "Only A 2", email="a2@only.example")
    assert any(i["kind"] == "new_leads" for i in _suggestions(a)["items"])
    assert _suggestions(b)["items"] == []
    gid = next(i["id"] for i in _suggestions(a)["items"])
    assert requests.post(f"{API}/campaigns/suggestions/{gid}/create", headers=b).status_code == 404
