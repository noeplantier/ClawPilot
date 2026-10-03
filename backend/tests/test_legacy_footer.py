"""Legacy send paths (single, batch, campaign step) append identity, data origin and a working unsubscribe link.

Runs on a server whose OUTREACH_SENDER_* are set (see .github/workflows/ci.yml). Nothing leaves the process (mock).
"""

import os
import re
import uuid

import pytest
import requests
from helpers import open_send_limits, unique_email

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
LINK = re.compile(r"https?://\S+/api/unsubscribe/(\S+)")


@pytest.fixture()
def org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"foot_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Footer Tester",
            "organization_name": f"Footer Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    open_send_limits(headers)
    return headers


def _lead(h, source="Salon 2025"):
    body = {"full_name": f"Foot Lead {uuid.uuid4().hex[:6]}", "email": unique_email("f")}
    if source:
        body["source"] = source
    resp = requests.post(f"{API}/leads", headers=h, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _messages(h):
    return requests.get(f"{API}/messages", headers=h).json()


def test_a_single_send_to_a_lead_carries_the_footer_and_the_link_unsubscribes():
    org = requests.post(
        f"{API}/auth/register",
        json={
            "email": unique_email("o"),
            "password": uuid.uuid4().hex,
            "full_name": "O",
            "organization_name": "Foot O",
        },
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {org}"}
    open_send_limits(h)
    lead_id = _lead(h)
    to = requests.get(f"{API}/leads/{lead_id}", headers=h).json()["email"]
    sent = requests.post(
        f"{API}/messages/email", headers=h, json={"to": to, "subject": "Hi", "body": "Hello", "lead_id": lead_id}
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()["message"]["body"]
    assert "CI Sender — CI Company SAS — 1 rue Fictive, 69000 Lyon" in body
    assert "Origine de vos données : Salon 2025." in body
    match = LINK.search(body)
    assert match, body

    assert requests.post(f"{API}/unsubscribe/{match.group(1)}").status_code == 200  # one-click (RFC 8058)
    again = requests.post(
        f"{API}/messages/email", headers=h, json={"to": to, "subject": "Hi", "body": "Hello", "lead_id": lead_id}
    )
    assert again.status_code in (403, 409), again.text  # opted out: refused, nothing recorded as sent


def test_the_origin_is_stated_as_unrecorded_when_the_lead_has_no_source(org):
    lead_id = _lead(org, source=None)
    to = requests.get(f"{API}/leads/{lead_id}", headers=org).json()["email"]
    sent = requests.post(
        f"{API}/messages/email", headers=org, json={"to": to, "subject": "Hi", "body": "Yo", "lead_id": lead_id}
    )
    assert "source non renseignée" in sent.json()["message"]["body"]


def test_a_batch_appends_the_footer_per_lead_and_skips_the_unsubscribed(org):
    leads = [_lead(org) for _ in range(2)]
    resp = requests.post(
        f"{API}/messages/email/batch",
        headers=org,
        json={"lead_ids": leads, "subject": "Hi {{first_name}}", "body": "Bonjour {{first_name}}"},
    )
    assert resp.json()["dispatched"] == 2
    bodies = [m["body"] for m in _messages(org)]
    tokens = {LINK.search(b).group(1) for b in bodies}
    assert len(tokens) == 2 and all("Origine de vos données" in b for b in bodies)

    requests.get(f"{API}/unsubscribe/{next(iter(tokens))}")
    again = requests.post(
        f"{API}/messages/email/batch", headers=org, json={"lead_ids": leads, "subject": "Hi", "body": "Again"}
    ).json()
    assert again["dispatched"] == 1 and again["skipped"] == 1


def test_a_campaign_step_appends_the_footer(org):
    lead_id = _lead(org)
    step = {"channel": "email", "delay_hours": 0, "subject": "Hello", "body": "Hi {{first_name}}", "language": "en"}
    cid = requests.post(f"{API}/campaigns", headers=org, json={"name": "Foot", "steps": [step]}).json()["id"]
    requests.post(f"{API}/campaigns/{cid}/assign-leads", headers=org, json={"lead_ids": [lead_id]})
    assert requests.post(f"{API}/campaigns/{cid}/run-step/0", headers=org).json()["dispatched"] == 1
    body = next(m["body"] for m in _messages(org) if m["channel"] == "email")
    assert LINK.search(body) and "CI Company SAS" in body


def test_a_forged_unsubscribe_token_is_rejected():
    assert requests.get(f"{API}/unsubscribe/not-a-token.abc").status_code == 404
