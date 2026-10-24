"""Live sending (SMTP) end to end, WITHOUT a network: the dispatch and the test-send run in this process on the real
database; the real SMTP library is replaced by a recorder, or the adapter by a fake. Nothing is ever delivered.

What is pinned here: the `sending` marker is committed BEFORE anything can leave (at most once), a failed attempt can be
retried but an unknown outcome never is, the sandbox allowlist, the kill switch, and the test-send restrictions.
Needs the server (to create the organisation and its drafts) and DATABASE_URL (the same database) like the other
integration tests; the server itself stays in dry-run.
"""

import asyncio
import os
import secrets
import smtplib
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests

if not os.environ.get("DATABASE_URL"):
    pytest.skip("needs DATABASE_URL (same database as the server)", allow_module_level=True)

from fastapi import HTTPException  # noqa: E402

from models import SmtpCheckIn  # noqa: E402
from repositories import draft_repo  # noqa: E402
from routes import outbound as outbound_routes  # noqa: E402
from services import smtp_svc  # noqa: E402
from services.outreach_os import dispatch  # noqa: E402
from services.outreach_os.channels import SendResult  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
FAKE_PASSWORD = secrets.token_hex(12)  # generated per run: never a literal credential in the repository
OWN = "founder@plantiers.com"
ALICE = "bonjour@latable-alice.example"  # La Table d'Alice, from the local fixture directory


@pytest.fixture(autouse=True)
def live_env(monkeypatch):
    """A production-like configuration, in this process only. The sender identity (name, company, address) must be the
    server's own, because the drafts it writes are checked against it: it comes from the same environment."""
    if not all(os.environ.get(f"OUTREACH_SENDER_{k}") for k in ("NAME", "COMPANY", "ADDRESS")):
        pytest.skip("needs OUTREACH_SENDER_NAME/_COMPANY/_ADDRESS, the same as the server (see ci.yml)")
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("OUTREACH_SENDER_EMAIL", OWN)
    for name in ("SEND_KILL_SWITCH", "OUTREACH_SANDBOX", "OUTREACH_LIVE_ALLOWLIST"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"live_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Live Tester",
            "organization_name": f"Live Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert requests.post(f"{API}/prospects/discovery/run", headers=headers, json={}).status_code == 200
    limits = requests.put(f"{API}/outbound/limits", headers=headers, json={"min_delay_seconds": 0})
    assert limits.status_code == 200, limits.text
    me = requests.get(f"{API}/auth/me", headers=headers).json()["user"]
    return {"headers": headers, "account_id": uuid.UUID(me["org_id"]), "user": me}


def _approved_draft(org, name="La Table d'Alice") -> str:
    h = org["headers"]
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    pid = next(p["id"] for p in items if p["name"] == name)
    assert requests.post(f"{API}/prospects/{pid}/review", headers=h, json={"decision": "approve"}).status_code == 200
    draft = requests.post(f"{API}/prospects/{pid}/drafts", headers=h)
    assert draft.status_code == 200, draft.text
    did = draft.json()["id"]
    reviewed = requests.post(f"{API}/prospects/drafts/{did}/review", headers=h, json={"decision": "approve"})
    assert reviewed.status_code == 200, reviewed.text
    return did


class FakeAdapter:
    """A real-looking adapter that records what happened around the call, with a scripted outcome."""

    channel, name, dry_run = "email", "smtp", False

    def __init__(self, org, *results):
        self.org, self.results, self.calls, self.seen_while_sending = org, list(results), [], []

    def send(self, message):
        self.calls.append(message)
        # Runs in a worker thread, against the server's committed view: is the marker visible BEFORE the send ends?
        rows = requests.get(f"{API}/outbound", headers=self.org["headers"]).json()
        self.seen_while_sending.append([r["status"] for r in rows])
        outcome = (
            self.results.pop(0)
            if self.results
            else SendResult("sent", f"<id{len(self.calls)}@plantiers.com>", simulated=False)
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _dispatch(org, draft_id, adapter, key=None):
    async def go(session):
        draft = await draft_repo.get(session, org["account_id"], draft_id)
        return await dispatch.dispatch_draft(
            session,
            org["account_id"],
            draft,
            now=datetime.now(timezone.utc),
            user_id=None,
            idempotency_key=key,
            live_adapter=adapter,
        )

    return run_async(go)


def _history(org):
    return requests.get(f"{API}/outbound", headers=org["headers"]).json()


def _allow(monkeypatch, *entries):
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", ",".join(entries))


# ---------------------------------------------------------------- dispatch, live
def test_the_marker_is_committed_before_the_send_and_the_result_replaces_it(org, monkeypatch):
    _allow(monkeypatch, ALICE)
    adapter = FakeAdapter(org)
    message, created = _dispatch(org, _approved_draft(org), adapter)

    assert created and len(adapter.calls) == 1
    assert adapter.seen_while_sending == [["sending"]]  # visible to another connection while the adapter was running
    assert message.status == "sent" and message.dry_run is False and message.adapter == "smtp"
    assert message.provider_message_id == "<id1@plantiers.com>"
    sent = adapter.calls[0]
    assert sent.to == ALICE and sent.sender_email == OWN and "api/unsubscribe/" in sent.body
    assert "List-Unsubscribe" in sent.headers
    assert [m["status"] for m in _history(org)] == ["sent"]


def test_a_replay_never_sends_twice(org, monkeypatch):
    _allow(monkeypatch, ALICE)
    adapter = FakeAdapter(org)
    did = _approved_draft(org)
    first, _ = _dispatch(org, did, adapter)
    again, created = _dispatch(org, did, adapter)
    other_key, created_other = _dispatch(org, did, adapter, key=uuid.uuid4().hex)
    assert again.id == other_key.id == first.id and not created and not created_other
    assert len(adapter.calls) == 1


def test_a_failed_attempt_can_be_dispatched_again_and_only_the_success_counts(org, monkeypatch):
    _allow(monkeypatch, ALICE)
    did = _approved_draft(org)
    adapter = FakeAdapter(org, SendResult("failed", None, "authentication failed (535)", simulated=False))
    failed, _ = _dispatch(org, did, adapter)
    assert failed.status == "failed" and failed.error == "authentication failed (535)"
    status = requests.get(f"{API}/outbound/status", headers=org["headers"]).json()
    assert status["sent_today"] == 0  # a failure does not use up the quota

    retried, created = _dispatch(org, did, adapter)  # the fixed credentials: a new attempt on the same draft
    assert created and retried.id != failed.id and retried.status == "sent" and len(adapter.calls) == 2
    replay, created = _dispatch(org, did, adapter)
    assert replay.id == retried.id and not created and len(adapter.calls) == 2


def test_an_unknown_outcome_stays_sending_and_is_never_retried(org, monkeypatch):
    _allow(monkeypatch, ALICE)
    did = _approved_draft(org)
    adapter = FakeAdapter(org, SendResult("unknown", None, "connection lost while sending: outcome unknown", False))
    message, created = _dispatch(org, did, adapter)
    assert created and message.status == "sending" and "outcome unknown" in message.error

    again, created = _dispatch(org, did, adapter)
    assert again.id == message.id and not created and len(adapter.calls) == 1  # nothing was sent a second time
    assert [m["status"] for m in _history(org)] == ["sending"]
    # It may well have left, so it counts toward the limits.
    assert requests.get(f"{API}/outbound/status", headers=org["headers"]).json()["sent_today"] == 1


def test_an_adapter_that_raises_is_treated_as_an_unknown_outcome_not_a_failure(org, monkeypatch):
    _allow(monkeypatch, ALICE)
    did = _approved_draft(org)
    message, _ = _dispatch(org, did, FakeAdapter(org, RuntimeError("boom with secret-token-123")))
    assert message.status == "sending" and "RuntimeError" in message.error
    assert "secret-token-123" not in message.error  # only the exception type is kept


# ---------------------------------------------------------------- guards
def test_the_sandbox_refuses_a_recipient_outside_the_allowlist(org, monkeypatch):
    _allow(monkeypatch, "someone-else@plantiers.com")
    adapter = FakeAdapter(org)
    with pytest.raises(dispatch.DispatchBlocked) as blocked:
        _dispatch(org, _approved_draft(org), adapter)
    assert blocked.value.code == "sandbox_recipient" and adapter.calls == []
    assert _history(org) == []


def test_an_empty_allowlist_allows_nobody_and_turning_the_sandbox_off_is_explicit(org, monkeypatch):
    did = _approved_draft(org)
    adapter = FakeAdapter(org)
    with pytest.raises(dispatch.DispatchBlocked) as blocked:
        _dispatch(org, did, adapter)
    assert blocked.value.code == "sandbox_recipient"

    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    message, _ = _dispatch(org, did, adapter)
    assert message.status == "sent" and len(adapter.calls) == 1


def test_live_sending_without_a_configured_adapter_is_refused(org, monkeypatch):
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    with pytest.raises(dispatch.DispatchBlocked) as blocked:
        _dispatch(org, _approved_draft(org), None)
    assert blocked.value.code == "live_not_available" and "SMTP" in blocked.value.message
    assert _history(org) == []


def test_the_kill_switch_stops_a_live_send_before_the_adapter(org, monkeypatch):
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    adapter = FakeAdapter(org)
    with pytest.raises(dispatch.DispatchBlocked) as blocked:
        _dispatch(org, _approved_draft(org), adapter)
    assert blocked.value.code == "kill_switch" and adapter.calls == []


# ---------------------------------------------------------------- test-send (real adapter, fake smtplib)
class FakeSMTP:
    instances: list = []
    fail: dict = {}

    def __init__(self, host, port, timeout=None, context=None):
        self.calls, self.sent = [], None
        FakeSMTP.instances.append(self)

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        if "login" in FakeSMTP.fail:
            raise FakeSMTP.fail["login"]

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.sent = (msg, from_addr, to_addrs)

    def quit(self):
        pass

    def close(self):
        pass


@pytest.fixture()
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail = [], {}
    for name, value in {"SMTP_HOST": "smtp.example", "SMTP_USERNAME": OWN, "SMTP_PASSWORD": FAKE_PASSWORD}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(smtp_svc.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def _test_send(org, to):
    async def go(session):
        return await outbound_routes.smtp_test_send(SmtpCheckIn(to=to), user={**org["user"]}, session=session)

    return run_async(go)


def test_test_send_goes_through_the_real_adapter_to_the_sender_only(org, smtp):
    result = _test_send(org, OWN)
    assert result.status == "sent" and result.adapter == "smtp" and result.to == OWN
    msg, from_addr, to_addrs = smtp.instances[0].sent
    assert (from_addr, to_addrs) == (OWN, [OWN]) and msg["Subject"] == outbound_routes.TEST_SUBJECT
    body = msg.get_content()
    assert os.environ["OUTREACH_SENDER_COMPANY"] in body and os.environ["OUTREACH_SENDER_ADDRESS"] in body  # identity
    assert "unsubscribe" in msg["List-Unsubscribe"]

    # It is recorded (so it counts toward the limits) but it is not an outreach event.
    messages = requests.get(f"{API}/messages", headers=org["headers"], params={"channel": "email"}).json()
    assert [m["status"] for m in messages] == ["sent"]
    assert requests.get(f"{API}/outbound/status", headers=org["headers"]).json()["sent_today"] == 1


def test_test_send_refuses_a_stranger_even_when_the_sandbox_is_off(org, smtp, monkeypatch):
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    with pytest.raises(HTTPException) as refused:
        _test_send(org, "prospect@restaurant.example")
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "sandbox_recipient"
    assert smtp.instances == []


def test_test_send_accepts_an_allowlisted_address(org, smtp, monkeypatch):
    _allow(monkeypatch, "colleague@plantiers.com")
    assert _test_send(org, "colleague@plantiers.com").status == "sent"


def test_test_send_reports_a_failed_login_without_the_password(org, smtp):
    smtp.fail = {"login": smtplib.SMTPAuthenticationError(535, f"bad credentials {FAKE_PASSWORD}".encode())}
    result = _test_send(org, OWN)
    assert result.status == "failed" and "535" in result.error and FAKE_PASSWORD not in result.error
    messages = requests.get(f"{API}/messages", headers=org["headers"], params={"channel": "email"}).json()
    assert [m["status"] for m in messages] == ["failed"]  # a failed test does not use up the quota
    assert requests.get(f"{API}/outbound/status", headers=org["headers"]).json()["sent_today"] == 0


@pytest.mark.parametrize(
    "setup, code, status",
    [
        ({"FEATURE_LIVE_SENDING": "false"}, "live_not_available", 501),
        ({"SMTP_PASSWORD": ""}, "live_not_available", 501),
        ({"SEND_KILL_SWITCH": "true"}, "kill_switch", 423),
        ({"OUTREACH_SENDER_COMPANY": ""}, "sender_not_configured", 409),
    ],
)
def test_test_send_refusals_are_explicit_and_send_nothing(org, smtp, monkeypatch, setup, code, status):
    for name, value in setup.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(HTTPException) as refused:
        _test_send(org, OWN)
    assert (refused.value.status_code, refused.value.detail["code"]) == (status, code)
    assert smtp.instances == []


def test_test_send_obeys_the_pause(org, smtp):
    assert (
        requests.put(f"{API}/outbound/limits", headers=org["headers"], json={"sending_paused": True}).status_code == 200
    )
    with pytest.raises(HTTPException) as refused:
        _test_send(org, OWN)
    assert refused.value.status_code == 423 and smtp.instances == []


# ---------------------------------------------------------------- over HTTP (the server stays in dry-run)
def test_the_http_test_send_is_closed_while_the_server_is_in_dry_run(org):
    h = org["headers"]
    assert requests.post(f"{API}/outbound/test-send", json={"to": OWN}).status_code == 401
    assert requests.post(f"{API}/outbound/test-send", headers=h, json={"to": "not-an-email"}).status_code == 422
    refused = requests.post(f"{API}/outbound/test-send", headers=h, json={"to": OWN})
    assert refused.status_code in (501, 409)  # dry-run, or no sender identity on this server
    assert refused.json()["detail"]["code"] in ("live_not_available", "sender_not_configured")


def test_the_event_loop_is_free_while_smtp_blocks(org, monkeypatch):
    """The adapter call is blocking: it must run in a worker thread, not on the event loop."""
    _allow(monkeypatch, ALICE)
    did = _approved_draft(org)
    ticks: list[int] = []
    during_send: list[int] = []

    class Slow(FakeAdapter):
        def send(self, message):
            before = len(ticks)
            time.sleep(0.4)
            during_send.append(len(ticks) - before)  # ticks the event loop managed while this call was blocked
            return super().send(message)

    async def go(session):
        draft = await draft_repo.get(session, org["account_id"], did)

        async def ticker():
            while True:
                await asyncio.sleep(0.05)
                ticks.append(1)

        task = asyncio.create_task(ticker())
        try:
            return await dispatch.dispatch_draft(
                session, org["account_id"], draft, now=datetime.now(timezone.utc), user_id=None, live_adapter=Slow(org)
            )
        finally:
            task.cancel()

    message, _ = run_async(go)
    assert message.status == "sent"
    assert during_send and during_send[0] >= 4, during_send  # a blocked loop would have ticked 0 times
