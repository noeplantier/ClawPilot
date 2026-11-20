"""Resend's signed events applied to the messages Resend carried: permanent bounces and complaints, nothing else.

The signature guard is covered offline in tests/unit/test_resend_svc.py. Here the effects on the database (in-process)
and the public route on the server under test (which has no RESEND_WEBHOOK_SECRET and is not production). No network.
"""

import uuid

import requests
from sqlalchemy import func, select

from db.models import Lead, OutboundEvent, OutboundMessage, SuppressionEntry
from services import resend_webhook
from tasks._bridge import run_async
from tests.prospect_fixtures import insert_rows, row
from tests.test_campaign_launch import API, _register


def _message(org, *, adapter="resend", status="sent"):
    """One message of this organisation, carried by `adapter`, with Resend's id. Returns (id, to, email_id)."""
    lead_id = uuid.UUID(insert_rows(org["account_id"], [row(f"Bistro {uuid.uuid4().hex[:6]}", "Lyon")])[0])
    email_id = str(uuid.uuid4())

    async def go(session):
        to = (await session.execute(select(Lead.email).where(Lead.id == lead_id))).scalar_one()
        message = OutboundMessage(
            account_id=org["account_id"],
            lead_id=lead_id,
            channel="email",
            to_email=to,
            subject="Bonjour",
            body="Un message.",
            adapter=adapter,
            dry_run=False,
            status=status,
            provider_message_id=email_id,
            idempotency_key=f"resend:{uuid.uuid4()}",
        )
        session.add(message)
        await session.commit()
        return message.id, to

    message_id, to = run_async(go)
    return message_id, to, email_id


def _apply(event, event_id=None):
    async def go(session):
        outcome = await resend_webhook.apply(session, event, event_id or f"msg_{uuid.uuid4().hex}")
        await session.commit()
        return outcome

    return run_async(go)


def _bounced(email_id, to, kind="Permanent"):
    return {"type": "email.bounced", "data": {"email_id": email_id, "to": [to], "bounce": {"type": kind}}}


def _state(org, message_id):
    async def go(session):
        status = (
            await session.execute(select(OutboundMessage.status).where(OutboundMessage.id == message_id))
        ).scalar()
        events = [
            e
            for e, in (
                await session.execute(select(OutboundEvent.event_type).where(OutboundEvent.message_id == message_id))
            ).all()
        ]
        suppressed = (
            await session.execute(
                select(func.count())
                .select_from(SuppressionEntry)
                .where(SuppressionEntry.account_id == org["account_id"])
            )
        ).scalar_one()
        return status, events, suppressed

    return run_async(go)


def test_a_permanent_bounce_marks_the_message_and_suppresses_the_address_once():
    org = _register("resend")
    message_id, to, email_id = _message(org)
    assert _apply(_bounced(email_id, to.upper()), "msg_one") == "bounced"  # the recipient is compared normalised
    assert _apply(_bounced(email_id, to), "msg_one") == "duplicate"  # the same event, delivered again
    status, events, suppressed = _state(org, message_id)
    assert status == "bounced" and events == ["bounced"] and suppressed == 1


def test_a_complaint_opts_the_prospect_out_and_counts_as_an_opposition():
    org = _register("resend")
    message_id, to, email_id = _message(org)
    event = {"type": "email.complained", "data": {"email_id": email_id, "to": [to]}}
    assert _apply(event) == "opted_out"
    status, events, suppressed = _state(org, message_id)
    assert status == "sent" and events == ["opted_out"] and suppressed >= 1


def test_what_is_not_a_permanent_bounce_or_a_complaint_about_this_message_changes_nothing():
    org = _register("resend")
    message_id, to, email_id = _message(org)
    assert _apply(_bounced(email_id, to, "Transient")) == "not_permanent"
    assert _apply(_bounced(email_id, "someone-else@other.example")) == "recipient_mismatch"
    assert _apply({"type": "email.delivered", "data": {"email_id": email_id, "to": [to]}}) == "ignored"
    assert _apply(_bounced(str(uuid.uuid4()), to)) == "unmatched"
    assert _apply({"type": "email.bounced", "data": {"to": [to]}}) == "no_email_id"
    smtp_id, smtp_to, smtp_email_id = _message(org, adapter="smtp")
    assert _apply(_bounced(smtp_email_id, smtp_to)) == "unmatched"  # only messages Resend carried
    assert _state(org, message_id) == ("sent", [], 0)
    assert _state(org, smtp_id) == ("sent", [], 0)


def test_the_public_route_needs_the_event_id_and_ignores_other_events():
    event = {"type": "email.delivered", "data": {"email_id": str(uuid.uuid4()), "to": ["a@b.example"]}}
    ok = requests.post(f"{API}/webhooks/resend", json=event, headers={"svix-id": f"msg_{uuid.uuid4().hex}"})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "outcome": "ignored"}
    missing = requests.post(f"{API}/webhooks/resend", json=event)
    assert missing.status_code == 200 and missing.json()["ok"] is False
