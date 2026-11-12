"""The send gate: no path may reach a provider without it. Offline, no database, no server."""

import ast
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import send_gate
from tasks import send_tasks

UTC = timezone.utc
BACKEND = Path(__file__).resolve().parents[2]
PROVIDER_CALLS = {"send_email", "send_whatsapp"}
# The provider modules define the senders; the Celery impls and routes are the call sites to guard.
EXEMPT = {Path("services/sendgrid_svc.py"), Path("services/twilio_svc.py"), Path("services/mail_provider.py")}


# ---- static guard ---------------------------------------------------------------------------------------
def _call_name(node: ast.Call):
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


# A local helper that only wraps `send_gate.check` (batch routes call it once per recipient).
GATE_WRAPPERS = {"_gate"}


def _is_gate_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Name):
        return f.id in GATE_WRAPPERS
    return (
        isinstance(f, ast.Attribute)
        and isinstance(f.value, ast.Name)
        and f.value.id == "send_gate"
        and f.attr in {"check", "assert_not_halted", "lock_and_assert_not_halted"}
    )


def _provider_call_sites():
    """(file, function name, first provider call line, first gate call line or None) for every call site."""
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        if rel.parts[0] in {"tests", "alembic", ".venv", "venv"} or rel in EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            own = [n for n in ast.walk(fn)]
            provider = [n.lineno for n in own if isinstance(n, ast.Call) and _call_name(n) in PROVIDER_CALLS]
            if not provider:
                continue
            gate = [n.lineno for n in own if _is_gate_call(n)]
            yield str(rel), fn.name, min(provider), min(gate) if gate else None


def test_every_provider_call_site_is_preceded_by_the_send_gate():
    sites = list(_provider_call_sites())
    assert sites, "the scan found no call site: the guard itself is broken"
    unguarded = [f"{f}:{line} {name}()" for f, name, line, gate in sites if gate is None or gate > line]
    assert not unguarded, (
        "These functions call a provider without going through services.send_gate first "
        f"(kill switch, pause, limits): {unguarded}"
    )


def test_gate_wrappers_really_call_the_gate():
    tree = ast.parse((BACKEND / "routes/messages.py").read_text(encoding="utf-8"))
    wrappers = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name in GATE_WRAPPERS]
    assert wrappers
    for fn in wrappers:
        assert any(
            _is_gate_call(n) and isinstance(n.func, ast.Attribute) for n in ast.walk(fn) if isinstance(n, ast.Call)
        ), f"{fn.name} must call send_gate.check"


def test_the_guard_covers_the_known_paths():
    files = {f for f, *_ in _provider_call_sites()}
    assert {"routes/messages.py", "routes/campaigns.py", "tasks/send_tasks.py"} <= files


# ---- day bounds -----------------------------------------------------------------------------------------
def test_day_bounds_follow_the_organisation_timezone():
    # 2026-06-01 23:30 UTC is already 2026-06-02 01:30 in Paris (UTC+2): the "day" there started at 22:00 UTC.
    start, end = send_gate.day_bounds(datetime(2026, 6, 1, 23, 30, tzinfo=UTC), "Europe/Paris")
    assert start == datetime(2026, 6, 1, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 6, 2, 22, 0, tzinfo=UTC)


def test_day_bounds_across_a_dst_change_is_a_calendar_day_not_24_hours():
    # Europe/Paris springs forward on 2026-03-29: that calendar day lasts 23 hours.
    start, end = send_gate.day_bounds(datetime(2026, 3, 29, 12, 0, tzinfo=UTC), "Europe/Paris")
    assert end - start == timedelta(hours=23)


def test_day_bounds_unknown_timezone_falls_back_to_utc():
    start, end = send_gate.day_bounds(datetime(2026, 6, 1, 15, 0, tzinfo=UTC), "Nowhere/Land")
    assert (start, end) == (datetime(2026, 6, 1, 0, 0, tzinfo=UTC), datetime(2026, 6, 2, 0, 0, tzinfo=UTC))


def test_check_rejects_an_unknown_channel():
    with pytest.raises(ValueError):
        asyncio.run(send_gate.check(None, None, "sms"))  # type: ignore[arg-type]


# ---- Celery: a refused send is rescheduled, never sent and never failed ---------------------------------
def test_retry_args_wait_for_the_limit_to_free_up():
    at = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)
    args = send_tasks._retry_args(send_gate.SendBlocked("limit_daily", "cap", retry_at=at))
    assert args == {"eta": datetime(2026, 6, 2, 8, 0), "max_retries": None}


def test_retry_args_for_a_halt_come_back_later_without_burning_the_retry_budget():
    args = send_tasks._retry_args(send_gate.SendBlocked("paused", "paused"))
    assert args == {"countdown": send_tasks.HALT_RETRY_SECONDS, "max_retries": None}


class _Retry(Exception):
    pass


class _Task:
    def retry(self, **kwargs):
        return _Retry(kwargs)


LEAD_ID = "00000000-0000-0000-0000-000000000001"


def _wire_impl(monkeypatch, blocked, provider_calls):
    lead = {
        "id": LEAD_ID,
        "email": "a@b.example",
        "phone": "+33600000000",
        "email_consent": "unknown",
        "whatsapp_consent": "opted_in",
        "contact_id": None,
        "country": None,
    }
    step = SimpleNamespace(id="s1", subject="Hi", body="Hello")
    campaign = SimpleNamespace(id="c1", status="running", steps=[step])

    async def get_campaign(*a, **k):
        return campaign

    async def get_leads(*a, **k):
        return [lead]

    async def no_window(*a, **k):
        return None

    async def gate(*a, **k):
        if blocked:
            raise blocked

    async def no_reply(*a, **k):
        return False

    async def no_lock(*a, **k):
        return None

    monkeypatch.setattr(send_tasks.campaign_repo, "get_campaign", get_campaign)
    monkeypatch.setattr(send_tasks.lead_repo, "get_leads_by_ids", get_leads)
    monkeypatch.setattr(send_tasks.outreach_repo, "has_inbound_reply", no_reply)
    monkeypatch.setattr(send_tasks.outreach_repo, "lock_lead_for_outreach", no_lock)
    monkeypatch.setattr(send_tasks, "_check_window_or_get_eta", no_window)
    monkeypatch.setattr(send_tasks.send_gate, "check", gate)

    def record(name):
        def fake(*a, **k):
            provider_calls.append(name)
            return {"status": "sent"}

        return fake

    async def prepare(*a, body, **k):  # the compliance envelope has its own tests (test_legacy_footer.py)
        return send_tasks.legacy_email.PreparedEmail(body)

    monkeypatch.setattr(send_tasks.legacy_email, "prepare", prepare)
    monkeypatch.setattr(send_tasks, "send_email", record("email"))
    monkeypatch.setattr("services.mail_provider.send_whatsapp", record("whatsapp"))


@pytest.mark.parametrize(
    "impl, channel", [(send_tasks._send_email_impl, "email"), (send_tasks._send_whatsapp_impl, "whatsapp")]
)
@pytest.mark.parametrize("code", ["paused", "kill_switch", "limit_daily"])
def test_a_blocked_task_retries_and_never_reaches_the_provider(monkeypatch, impl, channel, code):
    calls: list[str] = []
    retry_at = datetime(2026, 6, 2, 8, 0, tzinfo=UTC) if code.startswith("limit") else None
    _wire_impl(monkeypatch, send_gate.SendBlocked(code, "blocked", retry_at), calls)

    with pytest.raises(_Retry) as raised:
        asyncio.run(impl(None, _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))

    assert calls == []
    assert raised.value.args[0]["max_retries"] is None


@pytest.mark.parametrize(
    "impl, channel", [(send_tasks._send_email_impl, "email"), (send_tasks._send_whatsapp_impl, "whatsapp")]
)
def test_an_unblocked_task_reaches_the_provider_once(monkeypatch, impl, channel):
    calls: list[str] = []
    _wire_impl(monkeypatch, None, calls)

    async def ok(*a, **k):
        return None

    _wire_ledger(monkeypatch)
    for name in ("create_whatsapp_send", "record_outreach_event"):
        monkeypatch.setattr(send_tasks.outreach_repo, name, ok)
    monkeypatch.setattr(send_tasks.campaign_repo, "increment_counters", ok)

    result = asyncio.run(impl(_Session(), _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))
    assert result["status"] == "sent"
    assert calls == [channel]


class _Session:
    """Just enough of a session for the task: it commits the in-flight marker and flushes the outcome."""

    def __init__(self, events=None):
        self.events = events if events is not None else []

    async def commit(self):
        self.events.append("commit")

    async def flush(self):
        self.events.append("flush")


def _wire_ledger(monkeypatch, latest=None, rows=None):
    """The e-mail ledger without a database: `latest` is the previous attempt of this step to this address, `rows`
    collects what the task writes."""
    rows = rows if rows is not None else []

    async def latest_attempt(*a, **k):
        return latest

    async def create(*a, **k):
        row = SimpleNamespace(provider_message_id=None, error=None, **k)
        rows.append(row)
        return row

    monkeypatch.setattr(send_tasks.outreach_repo, "latest_email_attempt", latest_attempt)
    monkeypatch.setattr(send_tasks.outreach_repo, "create_email_send", create)
    return rows


def test_the_marker_is_committed_before_the_provider_is_called_and_completed_after(monkeypatch):
    events: list[str] = []
    _wire_impl(monkeypatch, None, events)
    rows = _wire_ledger(monkeypatch)

    async def ok(*a, **k):
        return None

    monkeypatch.setattr(send_tasks.outreach_repo, "record_outreach_event", ok)
    monkeypatch.setattr(send_tasks.campaign_repo, "increment_counters", ok)
    monkeypatch.setattr(
        send_tasks,
        "send_email",
        lambda *a, **k: events.append("provider")
        or {"status": "sent", "provider_id": "id-1", "error": None, "provider": "smtp", "ambiguous": False},
    )
    asyncio.run(send_tasks._send_email_impl(_Session(events), _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))
    assert events.index("commit") < events.index("provider")  # visible to everyone before anything can leave
    assert len(rows) == 1  # ONE row: a second would count twice against the daily and hourly caps
    assert (rows[0].status, rows[0].provider, rows[0].provider_message_id) == ("sent", "smtp", "id-1")


@pytest.mark.parametrize(
    "previous",
    [
        SimpleNamespace(status="queued", error=None),  # the process died after the marker: nobody knows
        SimpleNamespace(status="failed", error="connection lost while sending (OSError): outcome unknown"),
        SimpleNamespace(status="sent", error=None),
    ],
)
def test_a_retry_after_a_message_that_may_have_left_never_reaches_the_provider(monkeypatch, previous):
    calls: list[str] = []
    _wire_impl(monkeypatch, None, calls)
    rows = _wire_ledger(monkeypatch, latest=previous)
    result = asyncio.run(send_tasks._send_email_impl(_Session(), _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))
    assert result == {"status": "skipped", "reason": "already_attempted"}
    assert calls == [] and rows == []


def test_a_definitive_refusal_does_not_stop_a_later_attempt(monkeypatch):
    calls: list[str] = []
    _wire_impl(monkeypatch, None, calls)
    rows = _wire_ledger(
        monkeypatch, latest=SimpleNamespace(status="failed", error="the server refused the recipient address")
    )

    async def ok(*a, **k):
        return None

    monkeypatch.setattr(send_tasks.outreach_repo, "record_outreach_event", ok)
    monkeypatch.setattr(send_tasks.campaign_repo, "increment_counters", ok)
    result = asyncio.run(send_tasks._send_email_impl(_Session(), _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))
    assert result["status"] == "sent" and calls == ["email"] and len(rows) == 1


@pytest.mark.parametrize(
    "impl, channel", [(send_tasks._send_email_impl, "email"), (send_tasks._send_whatsapp_impl, "whatsapp")]
)
def test_a_replying_lead_is_stopped_before_any_sequence_channel_reaches_the_provider(monkeypatch, impl, channel):
    calls: list[str] = []
    _wire_impl(monkeypatch, None, calls)

    async def replied(*a, **k):
        return True

    monkeypatch.setattr(send_tasks.outreach_repo, "has_inbound_reply", replied)
    result = asyncio.run(impl(None, _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))
    assert result == {"status": "skipped", "reason": "recipient_replied"}
    assert calls == []


@pytest.mark.parametrize(
    "impl, channel", [(send_tasks._send_email_impl, "email"), (send_tasks._send_whatsapp_impl, "whatsapp")]
)
def test_a_task_without_a_provider_fails_with_the_reason_instead_of_retrying_forever(monkeypatch, impl, channel):
    calls: list[str] = []
    _wire_impl(monkeypatch, send_gate.SendBlocked("provider_not_configured", "no provider"), calls)

    result = asyncio.run(impl(None, _Task(), uuid.uuid4(), "c1", "s1", LEAD_ID))

    assert result == {"status": "failed", "reason": "provider_not_configured"}
    assert calls == []
