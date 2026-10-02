"""Outbound dispatch (dry-run) end to end on a running server: limits, pause, idempotency, unsubscribe, bounce,
replies, erasure. Nothing is sent: the only adapter is the dry-run one.

The server needs OUTREACH_SENDER_* set (see .github/workflows/ci.yml).
"""

import os
import re
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"ob_{uid}@test.com",
            "password": uuid.uuid4().hex,
            "full_name": "OB Tester",
            "organization_name": f"OB Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def org():
    h = _register()
    run = requests.post(f"{API}/prospects/discovery/run", headers=h, json={})
    assert run.status_code == 200, run.text
    return h


def _limits(h, **kw):
    resp = requests.put(f"{API}/outbound/limits", headers=h, json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _prospect(h, name):
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    return next(p["id"] for p in items if p["name"] == name)


def _draft(h, name, approve_draft=True):
    """Approve the prospect, prepare its draft, and (by default) approve the draft. Returns (prospect_id, draft_id)."""
    pid = _prospect(h, name)
    assert requests.post(f"{API}/prospects/{pid}/review", headers=h, json={"decision": "approve"}).status_code == 200
    draft = requests.post(f"{API}/prospects/{pid}/drafts", headers=h)
    assert draft.status_code == 200, draft.text
    did = draft.json()["id"]
    if approve_draft:
        r = requests.post(f"{API}/prospects/drafts/{did}/review", headers=h, json={"decision": "approve"})
        assert r.status_code == 200, r.text
    return pid, did


def _dispatch(h, draft_id, **headers):
    return requests.post(f"{API}/outbound/dispatch", headers={**h, **headers}, json={"draft_id": draft_id})


def _code(resp):
    return resp.json()["detail"]["code"]


def _events(h, mid):
    return requests.get(f"{API}/outbound/{mid}", headers=h).json()


# ---------------------------------------------------------------------------------------------------------
def test_defaults_are_conservative_and_dry_run(org):
    s = requests.get(f"{API}/outbound/status", headers=org).json()
    assert s["dry_run"] is True and s["kill_switch"] is False and s["paused"] is False
    assert s["limits"]["max_per_day"] == 20 and s["limits"]["min_delay_seconds"] == 60
    assert (s["sent_today"], s["sent_last_hour"], s["blocked_by"]) == (0, 0, None)
    assert requests.get(f"{API}/prospects/settings", headers=org).json()["flags"]["kill_switch"] is False


def test_dispatch_is_a_dry_run_and_idempotent(org):
    _limits(org, min_delay_seconds=0)
    pid, did = _draft(org, "La Table d'Alice")
    first = _dispatch(org, did)
    assert first.status_code == 200, first.text
    msg = first.json()
    assert msg["status"] == "sent" and msg["dry_run"] is True and msg["adapter"] == "dry_run_email"
    assert msg["provider_message_id"].startswith("dryrun-") and msg["to_email"] == "bonjour@latable-alice.example"
    assert msg["created"] is True

    detail = _events(org, msg["id"])
    assert "api/unsubscribe/" in detail["body"]
    assert [e["event_type"] for e in detail["events"]] == ["sent"]
    assert (
        detail["events"][0]["detail"]["dry_run"] is True and detail["events"][0]["detail"]["list_unsubscribe"] is True
    )

    again = _dispatch(org, did).json()
    other_key = _dispatch(org, did, **{"Idempotency-Key": uuid.uuid4().hex}).json()
    assert again["id"] == other_key["id"] == msg["id"] and again["created"] is False  # one draft, one message
    assert requests.get(f"{API}/outbound/status", headers=org).json()["sent_today"] == 1
    assert requests.get(f"{API}/prospects/settings", headers=org).json()["usage"]["messages_dispatched"] == 1
    assert len(requests.get(f"{API}/outbound", headers=org).json()) == 1


def test_unapproved_draft_or_prospect_is_refused_and_the_refusal_is_audited(org):
    pid, did = _draft(org, "La Table d'Alice", approve_draft=False)
    refused = _dispatch(org, did)
    assert refused.status_code == 409 and _code(refused) == "draft_not_approved"

    requests.post(f"{API}/prospects/drafts/{did}/review", headers=org, json={"decision": "approve"})
    requests.post(f"{API}/prospects/{pid}/review", headers=org, json={"decision": "reject"})
    assert _code(_dispatch(org, did)) == "prospect_not_approved"

    assert _dispatch(org, str(uuid.uuid4())).status_code == 404
    assert _dispatch(org, "not-a-uuid").status_code == 404
    events = requests.get(f"{API}/prospects/{pid}/events", headers=org).json()
    assert sum(e["action"] == "dispatch.blocked" for e in events) == 2  # committed even though the call failed
    assert requests.get(f"{API}/outbound", headers=org).json() == []


def test_minimum_delay_between_messages(org):
    _limits(org, min_delay_seconds=3600)
    _, d1 = _draft(org, "La Table d'Alice")
    _, d2 = _draft(org, "Chez Marcel")
    assert _dispatch(org, d1).status_code == 200
    blocked = _dispatch(org, d2)
    assert blocked.status_code == 429 and _code(blocked) == "limit_delay"
    assert blocked.json()["detail"]["retry_at"] and int(blocked.headers["Retry-After"]) > 3000
    assert requests.get(f"{API}/outbound/status", headers=org).json()["blocked_by"] == "delay"
    _limits(org, min_delay_seconds=0)
    assert _dispatch(org, d2).status_code == 200


def test_daily_and_hourly_limits(org):
    _limits(org, min_delay_seconds=0, max_per_day=1)
    _, d1 = _draft(org, "La Table d'Alice")
    _, d2 = _draft(org, "Chez Marcel")
    assert _dispatch(org, d1).status_code == 200
    daily = _dispatch(org, d2)
    assert daily.status_code == 429 and _code(daily) == "limit_daily"
    assert requests.get(f"{API}/outbound/status", headers=org).json()["blocked_by"] == "daily"

    _limits(org, max_per_day=10, max_per_hour=1)
    assert _code(_dispatch(org, d2)) == "limit_hourly"
    _limits(org, max_per_hour=100)
    assert _dispatch(org, d2).status_code == 200
    assert requests.get(f"{API}/outbound/status", headers=org).json()["sent_today"] == 2

    _limits(org, max_per_day=0)
    _, d3 = _draft(org, "Sushi Kaze")
    assert _code(_dispatch(org, d3)) == "limit_daily"  # zero means nothing may go out


def test_limit_validation(org):
    assert requests.put(f"{API}/outbound/limits", headers=org, json={}).status_code == 422
    for bad in ({"max_per_day": -1}, {"min_delay_seconds": 86401}, {"max_per_hour": "many"}):
        assert requests.put(f"{API}/outbound/limits", headers=org, json=bad).status_code == 422
    assert _limits(org, max_per_day=5)["max_per_day"] == 5
    assert requests.get(f"{API}/outbound/limits", headers=org).json()["max_per_day"] == 5


def test_account_pause_acts_as_a_kill_switch(org):
    _limits(org, min_delay_seconds=0)
    _, did = _draft(org, "La Table d'Alice")
    assert _limits(org, sending_paused=True)["sending_paused"] is True
    paused = _dispatch(org, did)
    assert paused.status_code == 423 and _code(paused) == "paused"
    s = requests.get(f"{API}/outbound/status", headers=org).json()
    assert s["paused"] is True and s["blocked_by"] == "paused"
    _limits(org, sending_paused=False)
    assert _dispatch(org, did).status_code == 200


def test_unsubscribe_takes_effect_before_the_next_dispatch(org):
    _limits(org, min_delay_seconds=0)
    pid, did = _draft(org, "La Table d'Alice")
    body = requests.get(f"{API}/prospects/{pid}", headers=org).json()["drafts"][0]["body"]
    token = re.search(r"/api/unsubscribe/(\S+)", body).group(1).rstrip(".")
    assert requests.get(f"{API}/unsubscribe/{token}").status_code == 200
    blocked = _dispatch(org, did)
    assert blocked.status_code == 409 and _code(blocked) == "suppressed"


def test_bounce_suppresses_the_address(org):
    _limits(org, min_delay_seconds=0)
    pid, did = _draft(org, "La Table d'Alice")
    mid = _dispatch(org, did).json()["id"]
    bounced = requests.post(f"{API}/outbound/{mid}/simulate", headers=org, json={"event": "bounced"})
    assert bounced.status_code == 200 and bounced.json()["status"] == "bounced"
    assert [e["event_type"] for e in _events(org, mid)["events"]] == ["sent", "bounced"]

    again = requests.post(f"{API}/outbound/{mid}/simulate", headers=org, json={"event": "replied", "text": "hi"})
    assert again.status_code == 409 and _code(again) == "already_bounced"
    assert (
        requests.post(f"{API}/prospects/{pid}/drafts", headers={**org, "Idempotency-Key": uuid.uuid4().hex}).status_code
        == 409
    )
    rerun = requests.post(f"{API}/prospects/discovery/run", headers=org, json={}).json()
    assert rerun["suppressed"] >= 1 and rerun["prospects_created"] == 0
    assert requests.get(f"{API}/outbound", headers=org, params={"status": "bounced"}).json()[0]["id"] == mid


def test_ordinary_reply_is_recorded_without_opting_out(org):
    _limits(org, min_delay_seconds=0)
    pid, did = _draft(org, "La Table d'Alice")
    mid = _dispatch(org, did).json()["id"]
    replied = requests.post(
        f"{API}/outbound/{mid}/simulate", headers=org, json={"event": "replied", "text": "Intéressé, rappelez-moi."}
    )
    assert replied.status_code == 200 and replied.json()["status"] == "replied"
    events = _events(org, mid)["events"]
    assert [e["event_type"] for e in events] == ["sent", "replied"]
    assert events[1]["detail"]["excerpt"].startswith("Intéressé")
    audit = [e for e in requests.get(f"{API}/prospects/{pid}/events", headers=org).json()]
    assert "Intéressé" not in str(audit)  # reply text stays out of the audit trail
    assert requests.get(f"{API}/prospects/{pid}", headers=org).json()["review_status"] == "approved"


def test_stop_reply_opts_out_immediately(org):
    _limits(org, min_delay_seconds=0)
    pid, did = _draft(org, "La Table d'Alice")
    mid = _dispatch(org, did).json()["id"]
    requests.post(f"{API}/outbound/{mid}/simulate", headers=org, json={"event": "replied", "text": "STOP"})
    assert [e["event_type"] for e in _events(org, mid)["events"]] == ["sent", "replied", "opted_out"]
    blocked = requests.post(f"{API}/prospects/{pid}/drafts", headers={**org, "Idempotency-Key": uuid.uuid4().hex})
    assert blocked.status_code == 409
    assert requests.post(f"{API}/prospects/discovery/run", headers=org, json={}).json()["suppressed"] >= 1


def test_simulate_validation(org):
    _limits(org, min_delay_seconds=0)
    _, did = _draft(org, "La Table d'Alice")
    mid = _dispatch(org, did).json()["id"]
    assert requests.post(f"{API}/outbound/{mid}/simulate", headers=org, json={"event": "delivered"}).status_code == 422
    assert (
        requests.post(f"{API}/outbound/{uuid.uuid4()}/simulate", headers=org, json={"event": "bounced"}).status_code
        == 404
    )


def test_erasure_blanks_the_outbound_record(org):
    _limits(org, min_delay_seconds=0)
    pid, did = _draft(org, "La Table d'Alice")
    mid = _dispatch(org, did).json()["id"]
    requests.post(f"{API}/outbound/{mid}/simulate", headers=org, json={"event": "replied", "text": "Bonjour Alice"})
    assert requests.post(f"{API}/prospects/{pid}/erase", headers=org).status_code == 204
    gone = _events(org, mid)
    assert gone["to_email"] is None and gone["body"] == "[erased]" and gone["subject"] == "[erased]"
    assert all(e["detail"] == {} for e in gone["events"])  # the reply excerpt is gone too
    assert gone["status"] == "replied"  # the fact that it happened is kept, the personal content is not


def test_organisations_are_isolated_for_dispatch():
    a, b = _register(), _register()
    for h in (a, b):
        requests.post(f"{API}/prospects/discovery/run", headers=h, json={})
    _limits(a, min_delay_seconds=0)
    _, did = _draft(a, "La Table d'Alice")
    mid = _dispatch(a, did).json()["id"]
    assert _dispatch(b, did).status_code == 404
    assert requests.get(f"{API}/outbound/{mid}", headers=b).status_code == 404
    assert requests.get(f"{API}/outbound", headers=b).json() == []
    assert requests.get(f"{API}/outbound/status", headers=b).json()["sent_today"] == 0
    assert requests.get(f"{API}/outbound/status").status_code in (401, 403)
