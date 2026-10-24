"""A real e-mail must be linked to a lead record: its footer carries that lead's unsubscribe link.

With a real provider configured (SMTP here, in this process only; nothing is ever sent) the single-send route answers
400 when no lead is given, and nothing is recorded. With the test sink (nothing can leave) the message is left
untouched. Needs the server (to create the organisation) and DATABASE_URL (the same database), like the other
in-process tests.
"""

import os
import secrets
import uuid

import pytest
import requests
from helpers import open_send_limits

if not os.environ.get("DATABASE_URL"):
    pytest.skip("needs DATABASE_URL (same database as the server)", allow_module_level=True)

from fastapi import HTTPException  # noqa: E402

from models import SendEmailIn  # noqa: E402
from routes import messages as message_routes  # noqa: E402
from services import legacy_email  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture()
def org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"env_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Envelope",
            "organization_name": f"Envelope {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    open_send_limits(headers)
    me = requests.get(f"{API}/auth/me", headers=headers).json()["user"]
    return {"headers": headers, "user": me, "account_id": uuid.UUID(me["org_id"])}


@pytest.fixture()
def smtp_provider(monkeypatch):
    """SMTP is the provider of this process: live sending on, SMTP_* complete (a host that cannot resolve), no sink."""
    monkeypatch.delenv("OUTREACH_TEST_SINK", raising=False)
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.invalid")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(12))  # generated per run: never a literal credential
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    monkeypatch.setenv("OUTREACH_SENDER_NAME", "Test Sender")
    monkeypatch.setenv("OUTREACH_SENDER_COMPANY", "Test Company SAS")
    monkeypatch.setenv("OUTREACH_SENDER_ADDRESS", "1 rue Fictive, 69000 Lyon")
    monkeypatch.setenv("OUTREACH_SENDER_EMAIL", "sender@example.test")


def _prepare(org, lead_id):
    return run_async(
        lambda session: legacy_email.prepare(
            session, org["account_id"], to_email="someone@example.test", body="Hello", lead_id=lead_id
        )
    )


@pytest.mark.parametrize("lead_id", [None, "", "not-a-uuid"])
def test_a_real_provider_refuses_a_message_without_a_lead(org, smtp_provider, lead_id):
    with pytest.raises(legacy_email.EmailNotCompliant) as refused:
        _prepare(org, lead_id)
    assert refused.value.code == "recipient_unknown"
    assert "lead_id is required" in refused.value.message


def test_a_lead_gets_the_footer_and_its_own_unsubscribe_link(org, smtp_provider):
    lead_id = str(uuid.uuid4())
    prepared = _prepare(org, lead_id)
    assert "Test Company SAS" in prepared.body and "1 rue Fictive, 69000 Lyon" in prepared.body
    assert "/api/unsubscribe/" in prepared.body and prepared.headers.get("List-Unsubscribe")


def test_the_test_sink_sends_nothing_so_it_leaves_the_message_untouched(org, smtp_provider, monkeypatch):
    monkeypatch.setenv("OUTREACH_TEST_SINK", "true")
    assert _prepare(org, None).body == "Hello"


def test_the_single_send_route_answers_400_without_a_lead_and_records_nothing(org, smtp_provider):
    payload = SendEmailIn(to="someone@test.example", subject="Hi", body="Hello")
    with pytest.raises(HTTPException) as refused:
        run_async(lambda session: message_routes.send_email_route(payload, user=org["user"], session=session))
    assert refused.value.status_code == 400
    assert "lead_id is required" in refused.value.detail
    assert requests.get(f"{API}/messages", headers=org["headers"]).json() == []
