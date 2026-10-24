"""Replies, bounces and STOP read from the sending mailbox, applied to real rows. No network: the mailbox is a fake.

The messages come from the dry-run dispatch; the inbound e-mails are built from the message's own Message-ID, like a
real mail client would answer. `sync` runs in this process against the same database as the server (DATABASE_URL).
"""

import asyncio
import os
import uuid

import pytest
import requests
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from db.url import async_database_url
from services import inbox_sync

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
OWN = "founder@plantiers.com"


class FakeMailbox:
    def __init__(self, raws):
        self.raws = raws
        self.seen: list[bytes] = []

    def fetch_unseen(self, limit=50):
        return [(str(i).encode(), raw) for i, raw in enumerate(self.raws, 1) if str(i).encode() not in self.seen]

    def mark_seen(self, uids):
        self.seen += uids


def _sync(mailbox):
    async def run():
        engine = create_async_engine(async_database_url(), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                return await inbox_sync.sync(session, mailbox)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _mail(*lines):
    return "\r\n".join(lines).encode()


def _reply(provider_id, sender, text, inbound=None):
    return _mail(
        f"From: {sender}",
        f"To: {OWN}",
        "Subject: Re: hello",
        f"Message-ID: <{inbound or uuid.uuid4().hex}@client.example>",
        f"In-Reply-To: <{provider_id}>",
        f"References: <{provider_id}>",
        "Content-Type: text/plain; charset=utf-8",
        "",
        text,
        "",
        "Le 3 oct., Noe a écrit :",
        "> quoted",
        "",
    )


def _bounce(provider_id, failed):
    return _mail(
        "From: MAILER-DAEMON@mx.example",
        f"To: {OWN}",
        "Subject: Undelivered",
        f"Message-ID: <{uuid.uuid4().hex}@mx.example>",
        "MIME-Version: 1.0",
        'Content-Type: multipart/report; report-type=delivery-status; boundary="B"',
        "",
        "--B",
        "Content-Type: text/plain",
        "",
        "failed",
        "--B",
        "Content-Type: message/delivery-status",
        "",
        "Reporting-MTA: dns; mx",
        "",
        f"Final-Recipient: rfc822; {failed}",
        "Action: failed",
        "Status: 5.1.1",
        "",
        "--B",
        "Content-Type: message/rfc822",
        "",
        f"Message-ID: <{provider_id}>",
        "Subject: x",
        "",
        "body",
        "--B--",
        "",
    )


@pytest.fixture()
def sent():
    """(headers, {name: message}) for two dry-run messages of a fresh organisation."""
    uid = uuid.uuid4().hex[:10]
    token = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"inb_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Inbox",
            "organization_name": f"Inbox {uid}",
        },
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert requests.post(f"{API}/prospects/discovery/run", headers=h, json={}).status_code == 200
    requests.put(f"{API}/outbound/limits", headers=h, json={"min_delay_seconds": 0})
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    out = {}
    for name in ("La Table d'Alice", "Chez Marcel"):
        pid = next(p["id"] for p in items if p["name"] == name)
        requests.post(f"{API}/prospects/{pid}/review", headers=h, json={"decision": "approve"})
        did = requests.post(f"{API}/prospects/{pid}/drafts", headers=h).json()["id"]
        requests.post(f"{API}/prospects/drafts/{did}/review", headers=h, json={"decision": "approve"})
        msg = requests.post(f"{API}/outbound/dispatch", headers=h, json={"draft_id": did})
        assert msg.status_code == 200, msg.text
        out[name] = msg.json()
    return h, out


def _new_draft_status(h, message):
    """409 once the prospect is suppressed or opted out: nothing new can be prepared for them."""
    return requests.post(f"{API}/prospects/{message['lead_id']}/drafts", headers=h).status_code


def _detail(h, message):
    return requests.get(f"{API}/outbound/{message['id']}", headers=h).json()


def test_a_reply_marks_the_message_replied_keeps_an_excerpt_and_is_recorded_once(sent):
    h, msgs = sent
    m = msgs["La Table d'Alice"]
    raw = _reply(m["provider_message_id"], m["to_email"], "Oui, appelez-moi demain.", inbound="same-id")
    box = FakeMailbox([raw, raw])
    result = _sync(box)
    assert result.replies == 1 and result.duplicates == 1 and result.opt_outs == 0
    detail = _detail(h, m)
    assert detail["status"] == "replied"
    replied = [e for e in detail["events"] if e["event_type"] == "replied"]
    assert len(replied) == 1 and replied[0]["detail"]["excerpt"] == "Oui, appelez-moi demain."
    assert "quoted" not in str(replied[0]["detail"])
    assert len(box.seen) == 2  # both flagged as read after the commit
    assert _sync(FakeMailbox([raw])).duplicates == 1  # a re-read of the same mail changes nothing


def test_a_stop_from_the_recipient_opts_the_prospect_out(sent):
    h, msgs = sent
    m = msgs["Chez Marcel"]
    result = _sync(FakeMailbox([_reply(m["provider_message_id"], m["to_email"], "STOP")]))
    assert result.opt_outs == 1
    assert "opted_out" in [e["event_type"] for e in _detail(h, m)["events"]]
    assert _new_draft_status(h, m) == 409


def test_a_stop_from_another_address_is_recorded_but_not_applied(sent):
    h, msgs = sent
    m = msgs["Chez Marcel"]
    result = _sync(FakeMailbox([_reply(m["provider_message_id"], "someone.else@other.example", "STOP")]))
    assert result.replies == 1 and result.opt_outs == 0
    events = _detail(h, m)["events"]
    assert "opted_out" not in [e["event_type"] for e in events]
    assert next(e for e in events if e["event_type"] == "replied")["detail"]["sender_matches_recipient"] is False


def test_a_hard_bounce_suppresses_the_address(sent):
    h, msgs = sent
    m = msgs["La Table d'Alice"]
    result = _sync(FakeMailbox([_bounce(m["provider_message_id"], m["to_email"])]))
    assert result.bounces == 1
    assert _detail(h, m)["status"] == "bounced"
    assert _new_draft_status(h, m) == 409


def test_a_bounce_about_another_address_and_unknown_mail_change_nothing(sent):
    h, msgs = sent
    m = msgs["La Table d'Alice"]
    stranger = _reply("not-ours@x.example", "x@y.example", "hello")
    result = _sync(FakeMailbox([_bounce(m["provider_message_id"], "other@client.example"), stranger]))
    assert result.bounces == 0 and result.unmatched == 1 and result.ignored == 1
    assert _detail(h, m)["status"] == "sent"


def test_the_manual_sync_endpoint_refuses_without_imap_and_needs_a_login():
    assert requests.post(f"{API}/outbound/sync-inbox").status_code in (401, 403)
    uid = uuid.uuid4().hex[:8]
    token = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"s_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "S",
            "organization_name": f"S {uid}",
        },
    ).json()["access_token"]
    resp = requests.post(f"{API}/outbound/sync-inbox", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 501 and "IMAP" in resp.json()["detail"]
    settings = requests.get(f"{API}/settings/integrations", headers={"Authorization": f"Bearer {token}"}).json()
    assert settings["outreach"]["imap_configured"] is False and settings["outreach"]["imap_host"] is None
