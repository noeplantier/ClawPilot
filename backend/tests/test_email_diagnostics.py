"""POST /api/settings/email/diagnostics on a running server: owner-triggered, nothing is sent, no secret comes back.

The server runs in the CI configuration (no SMTP, no IMAP, OUTREACH_TEST_SINK on: no DNS query either), so every
mailbox step is "skipped": the point here is the contract and the guards, not a live mailbox.
"""

import os
import uuid

import requests

API = f"{os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')}/api"


def _owner():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"diag_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Diag Tester",
            "organization_name": f"Diag Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_the_diagnosis_needs_a_signed_in_owner():
    assert requests.post(f"{API}/settings/email/diagnostics").status_code in (401, 403)


def test_the_diagnosis_reports_steps_and_notes_and_sends_nothing():
    h = _owner()
    resp = requests.post(f"{API}/settings/email/diagnostics", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"steps", "ok", "failed", "warnings", "notes", "checked_at"} <= set(body)
    assert any("Aucun message n'a été envoyé" in n for n in body["notes"])
    assert all({"id", "scope", "status", "detail"} == set(s) for s in body["steps"])
    assert {s["scope"] for s in body["steps"]} >= {"smtp", "imap"}
    assert body["failed"] == 0  # nothing configured: skipped, never reported as a failure or as a success
    # variable NAMES may be named (they say what to configure), values and addresses never are
    for value in (
        os.environ.get("OUTREACH_SENDER_EMAIL"),
        os.environ.get("SMTP_PASSWORD"),
        os.environ.get("IMAP_PASSWORD"),
    ):
        if value:
            assert value not in resp.text


def test_the_diagnosis_is_rate_limited_per_organisation():
    h = _owner()
    codes = [requests.post(f"{API}/settings/email/diagnostics", headers=h).status_code for _ in range(12)]
    assert codes[0] == 200 and 429 in codes
