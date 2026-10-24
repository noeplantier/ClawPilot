"""Settings > Integrations on a running server: one entry per integration, live database check, no network."""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED = {
    "database",
    "public_url",
    "osm",
    "geocoder",
    "registry",
    "sender",
    "sending_mode",
    "smtp",
    "imap",
    "sendgrid",
    "twilio",
    "twilio_webhook",
    "sendgrid_webhook",
    "ai",
}


def _headers():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"integ_{uid}@test.com",
            "password": uuid.uuid4().hex,
            "full_name": "Integration Tester",
            "organization_name": f"Integ Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_every_integration_is_listed_with_a_computed_status():
    data = requests.get(f"{API}/settings/integrations", headers=_headers()).json()
    items = {i["id"]: i for i in data["items"]}
    assert set(items) == EXPECTED
    assert sum(data["counts"].values()) == len(items)
    for item in items.values():
        assert item["status"] in {"ready", "unchecked", "partial", "missing", "blocked", "off"}
        assert item["label"] and item["summary"] and item["docs"].startswith("docs/integrations.md#")
        assert set(item["needs"]) <= set(item["env"]) | {"FEATURE_EXTERNAL_SOURCES"}
    assert data["generated_at"]


def test_database_is_checked_live_and_no_connection_detail_leaks():
    response = requests.get(f"{API}/settings/integrations", headers=_headers())
    db = {i["id"]: i for i in response.json()["items"]}["database"]
    assert db["status"] in {"ready", "partial"} and db["test"] == "server"
    assert any(k == "latency" for k, _ in db["facts"])
    url = os.environ.get("DATABASE_URL", "")
    if "@" in url:  # the credentials part of the URL must never appear in what Settings returns
        assert (
            url.split("@")[0].rsplit(":", 1)[-1] not in response.text or len(url.split("@")[0].rsplit(":", 1)[-1]) < 6
        )


def test_old_blocks_are_unchanged_and_consistent_with_the_entries():
    data = requests.get(f"{API}/settings/integrations", headers=_headers()).json()
    items = {i["id"]: i for i in data["items"]}
    assert (items["smtp"]["status"] in {"unchecked"}) == data["outreach"]["smtp_configured"]
    assert (items["sendgrid"]["status"] == "unchecked") == data["sendgrid_configured"]
    assert (items["twilio"]["status"] == "unchecked") == data["twilio_account_sid_configured"]
    assert (items["ai"]["status"] == "unchecked") == data["ai"]["active"]  # configured: testable, not yet tested
    assert (items["sender"]["status"] == "ready") == data["outreach"]["sender_configured"]


def test_the_database_test_runs_and_unknown_or_browser_ones_are_refused():
    headers = _headers()
    ok = requests.post(f"{API}/settings/integrations/database/test", headers=headers)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["id"] == "database" and body["ok"] is True and body["outcome"] == "passed"
    assert isinstance(body["latency_ms"], int) and body["checked_at"]
    assert requests.post(f"{API}/settings/integrations/geocoder/test", headers=headers).status_code == 400
    assert requests.post(f"{API}/settings/integrations/nope/test", headers=headers).status_code == 404


def test_unconfigured_services_are_skipped_without_any_network_call():
    headers = _headers()
    data = requests.get(f"{API}/settings/integrations", headers=headers).json()
    items = {i["id"]: i for i in data["items"]}
    for name in ("smtp", "imap", "sendgrid", "twilio", "registry", "ai"):
        if items[name]["status"] in {"missing", "off"}:  # not configured on the test server
            body = requests.post(f"{API}/settings/integrations/{name}/test", headers=headers).json()
            assert body["outcome"] == "skipped" and body["ok"] is False, name


def test_tests_need_a_login_and_are_rate_limited():
    assert requests.post(f"{API}/settings/integrations/database/test").status_code in (401, 403)
    headers = _headers()
    codes = [
        requests.post(f"{API}/settings/integrations/database/test", headers=headers).status_code for _ in range(12)
    ]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429
