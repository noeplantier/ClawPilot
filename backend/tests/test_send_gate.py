"""The legacy send paths (single, batch, campaign step, launch) obey the same pause and limits as the dispatch.

Runs on a server (see .github/workflows/ci.yml). Every test uses its own freshly registered organisation, so the
counters start at zero and the tests can be replayed on a database that has already been used. Nothing leaves the
process: without provider keys the senders return `mock`.
"""

import os
import threading
import uuid

import pytest
import requests
from helpers import unique_email

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

STEP_EMAIL = {"channel": "email", "delay_hours": 0, "subject": "Hello {{first_name}}", "body": "Hi", "language": "en"}
STEP_WHATSAPP = {"channel": "whatsapp", "delay_hours": 0, "body": "Hi {{first_name}}", "language": "en"}


@pytest.fixture()
def org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"gate_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Gate Tester",
            "organization_name": f"Gate Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _limits(h, channel="email", **kw):
    resp = requests.put(f"{API}/outbound/limits", params={"channel": channel}, headers=h, json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _lead(h, whatsapp=False):
    body = {"full_name": f"Gate Lead {uuid.uuid4().hex[:6]}", "email": unique_email("g")}
    if whatsapp:
        body.update(phone="+33612345678", whatsapp_opt_in=True, consent_source="test form")
    resp = requests.post(f"{API}/leads", headers=h, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _campaign(h, step, lead_ids):
    resp = requests.post(f"{API}/campaigns", headers=h, json={"name": "Gate Campaign", "steps": [step]})
    assert resp.status_code == 200, resp.text
    cid = resp.json()["id"]
    assert (
        requests.post(f"{API}/campaigns/{cid}/assign-leads", headers=h, json={"lead_ids": lead_ids}).status_code == 200
    )
    return cid


def _status(h, channel="email"):
    return requests.get(f"{API}/outbound/status", params={"channel": channel}, headers=h).json()


def _email(h, to=None):
    return requests.post(
        f"{API}/messages/email",
        headers=h,
        json={"to": to or unique_email("to"), "subject": "Hello", "body": "Hi there"},
    )


def _code(resp):
    return resp.json()["detail"]["code"]


# ---------------------------------------------------------------- single send
def test_a_paused_organisation_cannot_send_a_single_email(org):
    _limits(org, min_delay_seconds=0, sending_paused=True)
    refused = _email(org)
    assert refused.status_code == 423 and _code(refused) == "paused"
    assert requests.get(f"{API}/messages", headers=org).json() == []  # nothing was recorded as sent
    assert _status(org)["sent_today"] == 0

    _limits(org, sending_paused=False)
    assert _email(org).status_code == 200


def test_the_pause_covers_both_channels(org):
    _limits(org, sending_paused=True)
    refused = requests.post(f"{API}/messages/whatsapp", headers=org, json={"to": "+33612345678", "body": "hi"})
    assert refused.status_code == 423 and _code(refused) == "paused"


def test_the_daily_cap_applies_to_single_sends_and_the_refusal_is_audited(org):
    _limits(org, max_per_day=2, min_delay_seconds=0)
    assert _email(org).status_code == 200
    assert _email(org).status_code == 200
    refused = _email(org)
    assert refused.status_code == 429 and _code(refused) == "limit_daily"
    assert int(refused.headers["Retry-After"]) >= 1
    assert _status(org)["sent_today"] == 2


def test_the_minimum_delay_applies_to_single_sends(org):
    _limits(org, min_delay_seconds=3600)
    assert _email(org).status_code == 200
    refused = _email(org)
    assert refused.status_code == 429 and _code(refused) == "limit_delay"


def test_the_whatsapp_cap_is_independent_from_the_email_cap(org):
    _limits(org, "email", max_per_day=1, min_delay_seconds=0)
    _limits(org, "whatsapp", max_per_day=5, min_delay_seconds=0)
    assert _email(org).status_code == 200
    assert _code(_email(org)) == "limit_daily"
    wa = requests.post(f"{API}/messages/whatsapp", headers=org, json={"to": "+33612345678", "body": "hi"})
    assert wa.status_code == 200


# ---------------------------------------------------------------- batch
def test_a_batch_stops_at_the_cap_and_reports_what_was_not_attempted(org):
    _limits(org, max_per_day=2, min_delay_seconds=0)
    leads = [_lead(org) for _ in range(5)]
    resp = requests.post(
        f"{API}/messages/email/batch",
        headers=org,
        json={"lead_ids": leads, "subject": "Hi {{first_name}}", "body": "x"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dispatched"] == 2 and data["not_attempted"] == 3
    assert data["blocked"]["code"] == "limit_daily"
    assert [r["status"] for r in data["results"]].count("blocked") == 3
    assert _status(org)["sent_today"] == 2


def test_a_batch_on_a_paused_organisation_sends_nothing(org):
    _limits(org, min_delay_seconds=0, sending_paused=True)
    leads = [_lead(org) for _ in range(3)]
    data = requests.post(
        f"{API}/messages/email/batch", headers=org, json={"lead_ids": leads, "subject": "Hi", "body": "x"}
    ).json()
    assert data["dispatched"] == 0 and data["not_attempted"] == 3 and data["blocked"]["code"] == "paused"
    assert _status(org)["sent_today"] == 0


def test_a_whatsapp_batch_obeys_the_gate(org):
    _limits(org, "whatsapp", max_per_day=1, min_delay_seconds=0)
    leads = [_lead(org, whatsapp=True) for _ in range(3)]
    data = requests.post(f"{API}/messages/whatsapp/batch", headers=org, json={"lead_ids": leads, "body": "hi"}).json()
    assert data["dispatched"] == 1 and data["not_attempted"] == 2 and data["blocked"]["code"] == "limit_daily"


# ---------------------------------------------------------------- campaigns
def test_run_step_stops_at_the_cap_and_does_not_count_unsent_leads(org):
    _limits(org, max_per_day=2, min_delay_seconds=0)
    leads = [_lead(org) for _ in range(4)]
    cid = _campaign(org, STEP_EMAIL, leads)
    resp = requests.post(f"{API}/campaigns/{cid}/run-step/0", headers=org)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dispatched"] == 2 and data["not_attempted"] == 2 and data["blocked"]["code"] == "limit_daily"
    campaign = next(c for c in requests.get(f"{API}/campaigns", headers=org).json() if c["id"] == cid)
    assert campaign["sent"] == 2  # the counter only counts what really went out


def test_run_step_on_a_paused_organisation_sends_nothing(org):
    _limits(org, min_delay_seconds=0, sending_paused=True)
    cid = _campaign(org, STEP_EMAIL, [_lead(org), _lead(org)])
    data = requests.post(f"{API}/campaigns/{cid}/run-step/0", headers=org).json()
    assert data["dispatched"] == 0 and data["not_attempted"] == 2 and data["blocked"]["code"] == "paused"
    assert _status(org)["sent_today"] == 0


def test_launch_obeys_the_gate_and_reports_real_numbers(org):
    _limits(org, max_per_day=1, min_delay_seconds=0)
    cid = _campaign(org, STEP_EMAIL, [_lead(org), _lead(org), _lead(org)])
    resp = requests.post(f"{API}/campaigns/{cid}/launch", headers=org)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dispatched"] == 1 and data["total"] == 3 and data["not_attempted"] == 2
    assert data["blocked"]["code"] == "limit_daily"
    campaign = next(c for c in requests.get(f"{API}/campaigns", headers=org).json() if c["id"] == cid)
    assert campaign["sent"] == 1 and campaign["status"] == "running"
    # No fabricated engagement: opens, replies and conversions only ever come from webhooks.
    assert (campaign["opened"], campaign["replied"], campaign["converted"]) == (0, 0, 0)


def test_launch_without_a_step_or_without_leads_is_refused(org):
    no_step = requests.post(f"{API}/campaigns", headers=org, json={"name": "No step"}).json()["id"]
    assert requests.post(f"{API}/campaigns/{no_step}/launch", headers=org).status_code == 400
    no_lead = requests.post(f"{API}/campaigns", headers=org, json={"name": "No lead", "steps": [STEP_EMAIL]}).json()[
        "id"
    ]
    assert requests.post(f"{API}/campaigns/{no_lead}/launch", headers=org).status_code == 400


def test_a_whatsapp_campaign_step_obeys_the_gate(org):
    _limits(org, "whatsapp", max_per_day=1, min_delay_seconds=0)
    cid = _campaign(org, STEP_WHATSAPP, [_lead(org, whatsapp=True), _lead(org, whatsapp=True)])
    data = requests.post(f"{API}/campaigns/{cid}/run-step/0", headers=org).json()
    assert data["dispatched"] == 1 and data["not_attempted"] == 1 and data["blocked"]["code"] == "limit_daily"


# ---------------------------------------------------------------- shared counters, concurrency
def test_every_path_counts_toward_the_same_cap(org):
    _limits(org, max_per_day=3, min_delay_seconds=0)
    assert _email(org).status_code == 200  # single
    leads = [_lead(org) for _ in range(2)]
    batch = requests.post(
        f"{API}/messages/email/batch", headers=org, json={"lead_ids": leads, "subject": "x", "body": "y"}
    )
    assert batch.json()["dispatched"] == 2  # batch
    assert _status(org)["sent_today"] == 3

    cid = _campaign(org, STEP_EMAIL, [_lead(org)])
    step = requests.post(f"{API}/campaigns/{cid}/run-step/0", headers=org).json()  # campaign step
    assert step["dispatched"] == 0 and step["blocked"]["code"] == "limit_daily"
    assert _code(_email(org)) == "limit_daily"


def test_concurrent_sends_cannot_overshoot_the_cap(org):
    cap = 3
    _limits(org, max_per_day=cap, min_delay_seconds=0)
    codes: list[int] = []
    lock = threading.Lock()

    def worker():
        status = _email(org).status_code
        with lock:
            codes.append(status)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert codes.count(200) == cap, codes
    assert codes.count(429) == 10 - cap, codes
    assert _status(org)["sent_today"] == cap


def test_limits_are_per_organisation(org):
    _limits(org, max_per_day=1, min_delay_seconds=0)
    assert _email(org).status_code == 200
    assert _code(_email(org)) == "limit_daily"

    other = requests.post(
        f"{API}/auth/register",
        json={
            "email": unique_email("other"),
            "password": uuid.uuid4().hex,
            "full_name": "Other",
            "organization_name": f"Other {uuid.uuid4().hex[:6]}",
        },
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other}"}
    _limits(other_headers, min_delay_seconds=0)
    assert _email(other_headers).status_code == 200
