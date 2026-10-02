"""Activity feed now lives in PostgreSQL (audit_logs); new accounts start empty."""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _register():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": f"feed_{uid}@test.com",
            "password": uuid.uuid4().hex,  # random per run: no credential literal in the repo
            "full_name": "Feed Tester",
            "organization_name": f"Feed Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_new_account_starts_empty():
    headers = _register()
    assert requests.get(f"{BASE_URL}/api/leads", headers=headers).json() == []
    assert requests.get(f"{BASE_URL}/api/analytics/activity", headers=headers).json() == []


def test_activity_feed_records_actions_in_shape_and_order():
    headers = _register()
    for name in ("Alice", "Bob"):
        resp = requests.post(
            f"{BASE_URL}/api/leads",
            headers=headers,
            json={"full_name": name, "email": f"{name.lower()}_{uuid.uuid4().hex[:6]}@test.com", "company": "Acme"},
        )
        assert resp.status_code == 200, resp.text

    feed = requests.get(f"{BASE_URL}/api/analytics/activity", headers=headers).json()
    assert [a["kind"] for a in feed] == ["lead.created", "lead.created"]
    assert "Bob" in feed[0]["title"]  # newest first
    assert set(feed[0]) == {"id", "org_id", "kind", "title", "meta", "created_at"}

    assert len(requests.get(f"{BASE_URL}/api/analytics/activity?limit=1", headers=headers).json()) == 1


def test_activity_feed_is_scoped_per_organization():
    mine, other = _register(), _register()
    requests.post(
        f"{BASE_URL}/api/leads",
        headers=mine,
        json={"full_name": "Scoped", "email": f"scoped_{uuid.uuid4().hex[:6]}@test.com", "company": "Acme"},
    )
    assert requests.get(f"{BASE_URL}/api/analytics/activity", headers=other).json() == []


def test_inbound_whatsapp_webhook_lands_in_activity_feed():
    headers = _register()
    phone = f"+1415{uuid.uuid4().int % 10**7:07d}"
    lead = requests.post(
        f"{BASE_URL}/api/leads",
        headers=headers,
        json={
            "full_name": "Inbound",
            "email": f"in_{uuid.uuid4().hex[:6]}@test.com",
            "company": "Acme",
            "phone": phone,
        },
    )
    assert lead.status_code == 200, lead.text

    resp = requests.post(
        f"{BASE_URL}/api/webhooks/twilio",
        data={
            "MessageSid": f"SM{uuid.uuid4().hex}",
            "From": f"whatsapp:{phone}",
            "To": "whatsapp:+14155550000",
            "Body": "Hello",
        },
    )
    assert resp.status_code == 200, resp.text

    kinds = [a["kind"] for a in requests.get(f"{BASE_URL}/api/analytics/activity", headers=headers).json()]
    assert "whatsapp.inbound" in kinds


def test_integration_status_is_computed_not_hard_coded():
    headers = _register()
    data = requests.get(f"{BASE_URL}/api/settings/integrations", headers=headers).json()
    ai = data["ai"]
    assert ai["active"] == (ai["key_configured"] and ai["library_available"])
    assert ai["mode"] == ("live" if ai["active"] else "template")
    assert (ai["reason"] is None) == ai["active"]  # a reason is given exactly when it is not live
    out = data["outreach"]
    assert out["dry_run"] is True and out["kill_switch"] is False  # defaults of the test server
    assert out["sender_configured"] is True and out["sender_email"]
    assert set(data["webhooks"]) == {
        "production",
        "twilio_signature_ready",
        "twilio_webhook_url_set",
        "sendgrid_signature_ready",
    }
    assert requests.get(f"{BASE_URL}/api/settings/integrations").status_code in (401, 403)
