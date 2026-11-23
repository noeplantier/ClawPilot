"""Tranche 3: automatic mandate send queue. Offline: every provider/repository call is replaced by a fake."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services import mandate_send as ms

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)


def mandate(**overrides):
    values = dict(
        id=uuid.uuid4(), account_id=uuid.uuid4(), status="active",
        expires_at=NOW + timedelta(days=1), ai_budget=5, daily_volume=10,
        total_volume=100, time_windows=[{"start_hour": 8, "end_hour": 18}],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def message(status, *, when=None, draft_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(), status=status, draft_id=draft_id or uuid.uuid4(),
        dispatched_at=when or NOW - timedelta(minutes=1),
    )


def draft():
    return SimpleNamespace(id=uuid.uuid4(), status="approved")


@pytest.fixture
def gates(monkeypatch):
    """Healthy environment; each test changes only the one signal it is about."""
    leads = [uuid.uuid4()]
    sent = []

    async def policy(session, account_id, channel):
        return SimpleNamespace(sending_paused=False)

    async def hot(session, account_id, mandate_id):
        return leads

    async def ready(session, account_id, ids):
        return []

    async def opted_out(session, account_id, ids):
        return set()

    monkeypatch.setattr(ms.send_policy_repo, "get_policy", policy)
    monkeypatch.setattr(ms.imap_svc, "is_configured", lambda: True)
    monkeypatch.setattr(ms.feature_flags, "kill_switch", lambda: False)
    monkeypatch.setattr(ms, "hot_lead_ids", hot)
    monkeypatch.setattr(ms, "_ready_drafts", ready)
    monkeypatch.setattr(ms.launch_repo, "opted_out_message_lead_ids", opted_out)
    monkeypatch.setattr(ms, "_messages", lambda session, account_id, ids: asyncio.sleep(0, result=sent))
    return SimpleNamespace(leads=leads, messages=sent)


def test_mandate_windows_are_utc_and_authorise_nothing_when_empty():
    m = mandate()
    assert ms.in_window(m, NOW) is True
    assert ms.in_window(m, NOW.replace(hour=7)) is False
    assert ms.in_window(m, NOW.replace(hour=18)) is False
    assert ms.in_window(mandate(time_windows=[]), NOW) is False


def test_stop_reasons_come_only_from_real_signals(gates, monkeypatch):
    m = mandate()
    assert asyncio.run(ms.stop_reason(None, m, NOW)) is None
    assert asyncio.run(ms.stop_reason(None, mandate(expires_at=NOW - timedelta(seconds=1)), NOW)) == "expired"
    assert asyncio.run(ms.stop_reason(None, mandate(status="paused"), NOW)) == "paused"

    monkeypatch.setattr(ms.feature_flags, "kill_switch", lambda: True)
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "kill_switch"
    monkeypatch.setattr(ms.feature_flags, "kill_switch", lambda: False)

    monkeypatch.setattr(ms.imap_svc, "is_configured", lambda: False)
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "reply_collection_unavailable"
    monkeypatch.setattr(ms.imap_svc, "is_configured", lambda: True)

    gates.messages.append(message("replied"))
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "reply"
    gates.messages.clear()
    gates.messages.append(message("bounced"))
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "hard_bounce"
    gates.messages.clear()
    gates.messages.append(message("failed"))
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "provider_failure"
    gates.messages.clear()

    async def opted(session, account_id, ids):
        return {ids[0]}

    monkeypatch.setattr(ms.launch_repo, "opted_out_message_lead_ids", opted)
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "opposition"


def test_budget_and_volume_stop_the_mandate(gates, monkeypatch):
    m = mandate(ai_budget=1)
    one = draft()

    async def ready(session, account_id, ids):
        return [one]

    monkeypatch.setattr(ms, "_ready_drafts", ready)
    assert asyncio.run(ms.stop_reason(None, m, NOW)) == "ai_budget_reached"

    async def none(session, account_id, ids):
        return []

    monkeypatch.setattr(ms, "_ready_drafts", none)
    gates.messages.extend([message("sent"), message("sent")])
    assert asyncio.run(ms.stop_reason(None, mandate(daily_volume=2), NOW)) == "daily_volume_reached"
    assert asyncio.run(ms.stop_reason(None, mandate(total_volume=1), NOW)) == "total_volume_reached"


def test_apply_stop_persists_a_status_and_a_journal(monkeypatch):
    logged = {}

    async def log(session, account_id, **kw):
        logged.update(kw)

    monkeypatch.setattr(ms.audit_repo, "log", log)
    m = mandate()
    assert asyncio.run(ms.apply_stop(None, m, "hard_bounce", NOW)) == "revoked"
    assert m.status == "revoked" and m.updated_at == NOW
    assert logged["action"] == "mandate.auto_stop" and logged["diff"]["reason"] == "hard_bounce"


def test_snapshot_reports_real_states_and_only_approved_drafts(monkeypatch):
    approved, older = draft(), SimpleNamespace(id=uuid.uuid4(), status="draft")
    states = ["sending", "sent", "replied", "bounced", "failed"]
    messages = [message(state, draft_id=uuid.uuid4()) for state in states]

    async def ready(session, account_id, ids):
        return [approved]  # `draft` (not approved) is excluded by the real query

    async def hot(session, account_id, mandate_id):
        return [uuid.uuid4()]

    monkeypatch.setattr(ms, "_ready_drafts", ready)
    monkeypatch.setattr(ms, "hot_lead_ids", hot)
    monkeypatch.setattr(ms, "_messages", lambda session, account_id, ids: asyncio.sleep(0, result=messages))
    counts, planned = asyncio.run(ms.snapshot(None, mandate(), NOW))
    assert counts == {
        "planned": 1, "processing": 1, "accepted": 1, "failed": 1, "bounced": 1, "reply": 1,
    }
    assert planned == [approved]
    assert older.status == "draft"  # an unreviewed draft is never proposed


def test_send_due_never_retries_an_unclear_send(monkeypatch, gates):
    m = mandate()
    one = draft()
    calls = []

    async def ready(session, account_id, ids):
        return [one]

    async def existing(session, account_id, draft_id):
        return message("sending", draft_id=draft_id)  # outcome unknown

    async def dispatcher(session, account_id, d, **kw):
        calls.append(kw)
        return message("sent", draft_id=d.id), True

    async def log(session, account_id, **kw):
        return None

    monkeypatch.setattr(ms, "_ready_drafts", ready)
    monkeypatch.setattr(ms.outbound_repo, "get_for_draft", existing)
    monkeypatch.setattr(ms.audit_repo, "log", log)
    class Result:
        def scalars(self):
            return self

        def all(self):
            return [m]

    class Session:
        async def execute(self, statement):
            return Result()

    out = asyncio.run(ms.send_due(Session(), now=NOW, dispatcher=dispatcher))
    assert calls == [] and out["already"] == 1  # no second attempt after an unclear outcome


def test_send_due_uses_a_mandate_attributed_key_and_an_approved_draft(monkeypatch, gates):
    m = mandate()
    one = draft()
    calls = []

    async def ready(session, account_id, ids):
        return [one]

    async def none(session, account_id, draft_id):
        return None

    async def zero(session, account_id, draft_id):
        return 0

    async def dispatcher(session, account_id, d, **kw):
        calls.append((account_id, d.id, kw))
        return message("sent", draft_id=d.id), True

    async def log(session, account_id, **kw):
        return None

    async def one_mandate(session):
        return [m]  # used through the select path below

    monkeypatch.setattr(ms, "_ready_drafts", ready)
    monkeypatch.setattr(ms.outbound_repo, "get_for_draft", none)
    monkeypatch.setattr(ms.outbound_repo, "count_failed_for_draft", zero)
    monkeypatch.setattr(ms.audit_repo, "log", log)

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [m]

    class Session:
        async def execute(self, statement):
            return Result()

    out = asyncio.run(ms.send_due(Session(), now=NOW, dispatcher=dispatcher))
    assert len(calls) == 1
    assert calls[0][1] == one.id
    assert calls[0][2]["idempotency_key"] == f"mandate:{m.id}:{one.id}"
    assert out["accepted"] == 1  # adapter accepted, never labelled 'delivered'


def test_daily_report_counts_only_what_the_ledger_holds(monkeypatch):
    m = mandate()
    today = message("sent")
    old = message("replied", when=NOW - timedelta(days=3))
    logged = {}

    async def hot(session, account_id, mandate_id):
        return [uuid.uuid4()]

    async def messages(session, account_id, ids):
        return [today, old]

    async def log(session, account_id, **kw):
        logged.update(kw)

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [m]

    class Session:
        async def execute(self, statement):
            return Result()

    monkeypatch.setattr(ms, "hot_lead_ids", hot)
    monkeypatch.setattr(ms, "_messages", messages)
    monkeypatch.setattr(ms.audit_repo, "log", log)
    assert asyncio.run(ms.daily_report(Session(), now=NOW)) == {"mandates_reported": 1}
    assert logged["action"] == "mandate.daily_report"
    assert logged["diff"]["accepted"] == 1 and logged["diff"]["replies"] == 0


def test_beat_registers_the_send_task_on_the_sends_queue():
    from celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert beat["send-due-mandate-messages"]["task"] == "tasks.outreach_mandate_tasks.process_mandate_sends"
    assert beat["send-due-mandate-messages"]["options"]["queue"] == "sends"
    assert "mandate-daily-report" in beat
