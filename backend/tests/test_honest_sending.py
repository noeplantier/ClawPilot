"""Nothing pretends to be sent: the WhatsApp test route, the sandbox for phones, and the demo directory flag.

Runs on a server started like CI: OUTREACH_TEST_SINK records sends in-process (their ids start with `sink:`),
OUTREACH_LIVE_PHONES lists one fictional number, FEATURE_DEMO_DATA is on. No provider is ever called.
"""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
LISTED = "+33600000001"  # OUTREACH_LIVE_PHONES of the test server (a fictional number)


def _org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"honest_{uid}@test.com",
            "password": uuid.uuid4().hex,
            "full_name": "Honest Tester",
            "organization_name": f"Honest Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_the_whatsapp_test_reaches_only_a_listed_number_and_says_what_it_did():
    headers = _org()
    ok = requests.post(f"{API}/outbound/test-whatsapp", headers=headers, json={"to": LISTED})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["status"] == "sent" and body["to"] == LISTED and body["provider_message_id"].startswith("sink:")
    national = requests.post(f"{API}/outbound/test-whatsapp", headers=_org(), json={"to": "06 00 00 00 01"})
    assert national.status_code == 200 and national.json()["to"] == LISTED  # the national format is read, not guessed
    again = requests.post(f"{API}/outbound/test-whatsapp", headers=headers, json={"to": LISTED})
    assert again.status_code == 429 and again.json()["detail"]["code"] == "limit_delay"  # same limits as every send


def test_the_whatsapp_test_refuses_a_stranger_an_unreadable_number_and_an_anonymous_call():
    headers = _org()
    stranger = requests.post(f"{API}/outbound/test-whatsapp", headers=headers, json={"to": "+33611111111"})
    assert stranger.status_code == 422 and stranger.json()["detail"]["code"] == "sandbox_recipient"
    unreadable = requests.post(f"{API}/outbound/test-whatsapp", headers=headers, json={"to": "not a number"})
    assert unreadable.status_code == 422 and unreadable.json()["detail"]["code"] == "invalid_number"
    assert requests.post(f"{API}/outbound/test-whatsapp", json={"to": LISTED}).status_code in (401, 403)


def test_a_paused_organisation_cannot_run_the_whatsapp_test():
    headers = _org()
    assert requests.put(f"{API}/outbound/limits", headers=headers, json={"sending_paused": True}).status_code == 200
    refused = requests.post(f"{API}/outbound/test-whatsapp", headers=headers, json={"to": LISTED})
    assert refused.status_code == 423 and refused.json()["detail"]["code"] == "paused"


def test_the_server_reports_its_sending_mode_instead_of_a_pretend_one():
    data = requests.get(f"{API}/settings/integrations", headers=_org()).json()
    items = {i["id"]: i for i in data["items"]}
    assert "TEST SINK" in items["sending_mode"]["label"]  # the test server says it records, not sends
    for name in ("sendgrid", "twilio"):
        assert "MOCK" not in items[name]["label"] and "NOTHING IS SENT" in items[name]["label"]
    assert items["ai"]["label"] == "OFF · NOTHING IS GENERATED" and data["ai"]["mode"] == "off"


def test_the_demo_directory_is_a_flag_not_a_default():
    headers = _org()
    flags = requests.get(f"{API}/prospects/settings", headers=headers).json()["flags"]
    assert flags["demo_data"] is True  # on for the test server only
    names = [s["name"] for s in requests.get(f"{API}/sources", headers=headers).json()]
    assert "world_fixture" in names and "openstreetmap" in names  # offered because the flag is on here
