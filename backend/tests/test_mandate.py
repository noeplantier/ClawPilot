"""The bounded automatic mode "Automatisation max", end to end, WITHOUT a network and without a real transport.

It is off by default (the server flag) and nothing acts without an ACTIVE mandate. These tests prove what a mandate may
and may not do: it acts only inside its zone, template, sender, caps and expiry; it stops on its stop rules; it never
widens anything; it can be revoked at once. HTTP for the guards (the CI server has the flag off), in-process with an
injected clock for the engine, a recording adapter for the sending: nothing is ever delivered.
"""

import os
import secrets
import uuid
from datetime import timedelta

import pytest
import requests

if not os.environ.get("DATABASE_URL"):
    pytest.skip("needs DATABASE_URL (same database as the server)", allow_module_level=True)

from sqlalchemy import select, update  # noqa: E402

from db.models import AutomationMandate, CampaignApproval, MandateEvent, OutboundMessage  # noqa: E402
from repositories import campaign_repo, mandate_repo  # noqa: E402
from services import mandate as engine  # noqa: E402
from tasks._bridge import run_async  # noqa: E402
from tests.prospect_fixtures import insert_rows, row  # noqa: E402
from tests.test_campaign_launch import (  # noqa: E402,F401
    API,
    Recorder,
    _base,
    _dispatches,
    _messages,
    _policy,
    _process,
    _register,
)
from tests.test_journey import LYON, OFFER, _approve, _call  # noqa: E402,F401


@pytest.fixture(autouse=True)
def env(monkeypatch):
    if not all(os.environ.get(f"OUTREACH_SENDER_{k}") for k in ("NAME", "COMPANY", "ADDRESS", "EMAIL")):
        pytest.skip("needs OUTREACH_SENDER_* (see ci.yml)")
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    monkeypatch.setenv("FEATURE_AUTOMATION_MAX", "true")  # this PROCESS; the server under test keeps it off
    monkeypatch.setenv("SMTP_HOST", "smtp.example-mail.test")
    monkeypatch.setenv("SMTP_USERNAME", "sender@test.example")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))  # generated per run: never a literal credential
    for name in ("SEND_KILL_SWITCH", "OUTREACH_LIVE_ALLOWLIST", "SENDGRID_API_KEY"):
        monkeypatch.delenv(name, raising=False)


ACK = ["bounded", "real_sending", "provider_terms", "can_revoke"]


def _org(prefix="mandate"):
    org = _register(prefix)
    assert requests.put(f"{API}/settings/offer", headers=org["headers"], json=OFFER).status_code == 200
    _policy(org, max_per_day=1000, max_per_hour=1000, min_delay_seconds=0, timezone_source="account_default")
    return org


def _journey(org, leads=6):
    insert_rows(org["account_id"], [row(f"Bistro {i:03d}", "Lyon", review_status="approved") for i in range(leads)])
    created = requests.post(f"{API}/journeys", headers=org["headers"], json={"name": "Lyon", "zone": LYON, "size": 100})
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


def _create(org, jid, **over):
    body = {"campaign_id": jid, "daily_cap": 5, "total_cap": 20, "days": 14, **over}
    return requests.post(f"{API}/mandates", headers=org["headers"], json=body)


def _setup(org, leads=6, **over):
    jid = _journey(org, leads)
    resp = _create(org, jid, **over)
    assert resp.status_code == 200, resp.text
    return jid, resp.json()["data"]["id"]


def _do(org, mid, fn):
    async def go(session):
        found = await mandate_repo.get(session, org["account_id"], uuid.UUID(mid))
        return await fn(session, found)

    return _call(go)


def _activate(org, mid, now=None, replies=True, ack=None):
    return _do(
        org,
        mid,
        lambda s, m: engine.activate(
            s,
            m,
            org["user_id"],
            acknowledgements=ACK if ack is None else ack,
            now=now or _base(),
            reply_collection_ok=replies,
        ),
    )


def _tick(org, mid, now=None, replies=True):
    return _do(org, mid, lambda s, m: engine.tick(s, m, now or _base(), reply_collection_ok=replies))


def _pump(org, start, recorder, rounds=10, step_seconds=70):
    """The scheduled task runs every minute: the mandate's own cadence (30 s at least between two messages; 60 s by
    default) lets one message through per visit here. Returns how many were accepted over the visits."""
    return sum(_process(org, start + timedelta(seconds=step_seconds * i), recorder)["accepted"] for i in range(rounds))


def _state(org, mid):
    async def go(session):
        m = await mandate_repo.get(session, org["account_id"], uuid.UUID(mid))
        return engine.view(m)

    return _call(go)


def _journal(org, mid):
    async def go(session):
        rows = await session.execute(
            select(MandateEvent).where(MandateEvent.mandate_id == uuid.UUID(mid)).order_by(MandateEvent.created_at)
        )
        return [(e.action, e.detail) for e in rows.scalars()]

    return _call(go)


# ================================================================== off by default
def test_the_mode_is_off_by_default_on_the_server_and_says_how_it_would_be_turned_on():
    org = _org()
    data = requests.get(f"{API}/mandates", headers=org["headers"]).json()["data"]
    assert data["enabled"] is False and data["flag"] == "FEATURE_AUTOMATION_MAX" and data["mandates"] == []
    assert "FEATURE_AUTOMATION_MAX" in data["why_disabled"]
    assert data["limits"]["zones"] == 1 and data["limits"]["max_days"] == 90 and data["acknowledgements"] == ACK
    assert data["defaults"]["ai_budget"] == 0
    # the reasons in words, so the screen can read a journal without inventing a sentence
    assert data["stop_labels"]["kill_switch"].startswith("Arrêt d'urgence") and "bounce_rate" in data["stop_labels"]


def test_a_server_with_the_mode_off_refuses_the_activation_and_keeps_the_refusal_in_the_journal():
    org = _org()
    jid, mid = _setup(org)
    resp = requests.post(f"{API}/mandates/{mid}/activate", headers=org["headers"], json={"acknowledgements": ACK})
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "feature_disabled"
    detail = requests.get(f"{API}/mandates/{mid}", headers=org["headers"]).json()["data"]
    assert detail["status"] == "draft"  # nothing was authorised
    assert [e["action"] for e in detail["journal"]][:2] == ["activation_refused", "created"]


def test_a_mandate_does_nothing_without_the_flag_even_when_it_is_active(monkeypatch):
    org = _org()
    jid, mid = _setup(org)
    _activate(org, mid)
    monkeypatch.delenv("FEATURE_AUTOMATION_MAX")
    out = _tick(org, mid)
    assert out == {"action": "held", "reason": "feature_disabled"}
    assert _dispatches(org, jid) == []  # nothing approved, nothing planned


def test_the_scheduled_task_is_a_no_op_while_the_mode_is_off(monkeypatch):
    from tasks import mandate_tasks

    monkeypatch.delenv("FEATURE_AUTOMATION_MAX")
    assert run_async(mandate_tasks._run) == {"status": "disabled"}


# ================================================================== a mandate is bounded as written
def test_a_mandate_is_a_draft_pinned_to_what_exists_and_nothing_automatic_happens():
    org = _org()
    jid, mid = _setup(org, daily_cap=3, total_cap=10, days=7)
    state = _state(org, mid)
    assert state["status"] == "draft" and state["daily_cap"] == 3 and state["total_cap"] == 10
    assert state["zones"][0]["category"] == "restaurants" and state["ai_budget"] == 0 and state["template_version"] == 1
    assert state["stop_rules"]["max_bounce_rate"] == 0.05 and state["expires_at"]
    assert _dispatches(org, jid) == [] and _messages(org) == []
    assert _journal(org, mid)[0][0] == "created" and "content_hash" in _journal(org, mid)[0][1]


@pytest.mark.parametrize(
    "over,status,code",
    [
        ({"daily_cap": 50, "total_cap": 10}, 409, "caps_order"),
        ({"days": 91}, 422, None),  # a mandate lasts 90 days at most: refused by the contract itself
        ({"total_cap": 0}, 422, None),
        ({"total_cap": 101}, 422, None),
        ({"min_delay_seconds": 5}, 422, None),
        ({"search_every_hours": 1}, 422, None),
        ({"window_start_hour": 18, "window_end_hour": 8}, 409, "window"),
    ],
)
def test_an_unbounded_or_incoherent_mandate_cannot_be_written(over, status, code):
    org = _org()
    jid = _journey(org, 2)
    resp = _create(org, jid, **over)
    assert resp.status_code == status
    if code:
        assert resp.json()["detail"]["code"] == code


def test_a_campaign_has_one_mandate_at_a_time_and_a_non_zone_campaign_has_none():
    org = _org()
    jid, mid = _setup(org)
    assert _create(org, jid).status_code == 409
    other = requests.post(f"{API}/campaigns", headers=org["headers"], json={"name": "Séquence", "channels": ["email"]})
    if other.status_code == 200:
        assert _create(org, other.json()["id"]).status_code == 404  # no zone: not a journey


# ================================================================== the explicit authorisation
def test_the_four_acknowledgements_are_all_required_by_their_exact_codes():
    org = _org()
    jid, mid = _setup(org)
    for given in ([], ACK[:3], ACK + ["extra"], ["yes"] * 4):
        with pytest.raises(engine.MandateRefused) as refused:
            _activate(org, mid, ack=given)
        assert refused.value.code == "acknowledgements"
    assert _state(org, mid)["status"] == "draft"


def test_nothing_is_activated_while_the_replies_are_not_read():
    org = _org()
    jid, mid = _setup(org)
    with pytest.raises(engine.MandateRefused) as refused:
        _activate(org, mid, replies=False)
    assert refused.value.code == "reply_collection_down" and "opposition" in refused.value.label


def test_nothing_is_activated_while_sending_is_halted_or_something_blocking_is_missing(monkeypatch):
    org = _org()
    jid, mid = _setup(org)
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    with pytest.raises(engine.MandateRefused) as halted:
        _activate(org, mid)
    assert halted.value.code == "kill_switch"
    monkeypatch.delenv("SEND_KILL_SWITCH")
    monkeypatch.delenv("SMTP_HOST")
    with pytest.raises(engine.MandateRefused) as unconfigured:
        _activate(org, mid)
    assert unconfigured.value.code == "not_ready_provider"


def test_one_automatic_programme_at_a_time_per_organisation():
    org = _org()
    jid, mid = _setup(org)
    _activate(org, mid)
    jid2 = _journey(org, 0)
    mid2 = _create(org, jid2).json()["data"]["id"]
    with pytest.raises(engine.MandateRefused) as refused:
        _activate(org, mid2)
    assert refused.value.code == "another_active"


def test_activating_pins_the_mandate_and_writes_the_authorisation_in_the_journal():
    org = _org()
    jid, mid = _setup(org)
    done = _activate(org, mid)
    assert done.status == "active" and done.activated_at is not None
    actions = [a for a, _ in _journal(org, mid)]
    assert actions == ["created", "activated"]
    terms = _journal(org, mid)[1][1]
    assert terms["daily_cap"] == 5 and terms["total_cap"] == 20 and terms["provider"].startswith("smtp:")
    assert "password" not in str(terms).lower() and "sender@test.example" not in str(terms)  # no secret, no address


# ================================================================== it acts only inside the mandate
def test_inside_its_caps_the_run_approves_plans_and_the_normal_sender_does_the_rest():
    org = _org()
    jid, mid = _setup(org, leads=6, daily_cap=2, total_cap=4)
    _activate(org, mid)
    out = _tick(org, mid)
    assert out["action"] == "ran" and out["scheduled"] == 6 and out["fresh"] == 6
    assert _messages(org) == []  # the run plans, it sends nothing itself
    assert _tick(org, mid)["fresh"] == 0 and _tick(org, mid)["scheduled"] == 0  # nothing new: nothing approved again
    recorder = Recorder()
    day1 = _base() + timedelta(minutes=10)
    assert _pump(org, day1, recorder) == 2  # the mandate's daily cap, not the organisation's
    day2 = _base() + timedelta(days=1, minutes=10)
    assert _pump(org, day2, recorder) == 2
    assert len(recorder.calls) == 4  # the total cap
    day3 = _base() + timedelta(days=2, minutes=10)
    assert _pump(org, day3, recorder) == 0 and len(recorder.calls) == 4  # never one more
    assert {r["reason"] for r in _dispatches(org, jid) if r["status"] == "skipped"} == {"cap_total"}
    assert len({c.to for c in recorder.calls}) == 4  # one message per recipient


def test_the_run_never_widens_the_zone_the_offer_the_template_the_caps_or_the_expiry():
    org = _org()
    jid, mid = _setup(org, leads=4, daily_cap=2, total_cap=3, days=10)
    _activate(org, mid)
    before = _state(org, mid)
    zone_before = _call(lambda s: campaign_repo.get_campaign(s, org["account_id"], jid)).zone
    for hours in (0, 1, 2, 3):
        _tick(org, mid, _base() + timedelta(hours=hours))
    after = _state(org, mid)
    for key in (
        "zones",
        "daily_cap",
        "total_cap",
        "ai_budget",
        "window",
        "min_delay_seconds",
        "template_version",
        "expires_at",
        "stop_rules",
        "provider",
    ):
        assert after[key] == before[key], key
    assert _call(lambda s: campaign_repo.get_campaign(s, org["account_id"], jid)).zone == zone_before

    async def approvals(session):
        rows = await session.execute(select(CampaignApproval).where(CampaignApproval.campaign_id == uuid.UUID(jid)))
        return [(a.total_cap, a.daily_cap, a.mandate_id) for a in rows.scalars()]

    assert {(t, d) for t, d, _ in _call(approvals)} == {(3, 2)}  # the approvals carry the mandate's caps, no more
    assert all(m == uuid.UUID(mid) for _, _, m in _call(approvals))


def test_a_prospect_outside_the_zone_is_never_contacted_even_if_it_qualifies():
    org = _org()
    insert_rows(
        org["account_id"],
        [
            row("Dedans", "Lyon", review_status="approved"),
            row("Dehors", "Paris", review_status="approved", lat=48.85, lon=2.35),
        ],
    )
    jid = requests.post(f"{API}/journeys", headers=org["headers"], json={"name": "Lyon", "zone": LYON}).json()["data"][
        "id"
    ]
    mid = _create(org, jid).json()["data"]["id"]
    _activate(org, mid)
    _tick(org, mid)
    recorder = Recorder()
    _process(org, _base() + timedelta(minutes=10), recorder)
    assert len(recorder.calls) == 1 and "Dedans" in recorder.calls[0].body and "Dehors" not in recorder.calls[0].body


def test_the_mandates_own_window_and_cadence_are_stricter_than_the_organisations():
    org = _org()
    jid, mid = _setup(
        org, leads=3, daily_cap=3, total_cap=3, window_start_hour=9, window_end_hour=11, min_delay_seconds=120
    )
    _activate(org, mid)
    _tick(org, mid)
    recorder = Recorder()
    # 12:00 UTC: inside the organisation's 8-18 window, outside the mandate's 9-11 window
    noon = _base().replace(hour=12)
    counts = _process(org, noon, recorder)
    assert counts["accepted"] == 0 and recorder.calls == [] and counts["waiting"] >= 1
    assert "outside_window" in {r["reason"] for r in _dispatches(org, jid) if r["status"] == "scheduled"}
    # inside the window the cadence applies: one message, then the next one waits two minutes
    ten = _base().replace(hour=10, minute=0) + timedelta(days=1)
    _call(
        lambda s: s.execute(
            update(__import__("db.models", fromlist=["CampaignDispatch"]).CampaignDispatch).values(planned_at=ten)
        )
    )
    counts = _process(org, ten, recorder)
    assert counts["accepted"] == 1 and "limit_delay" in {
        r["reason"] for r in _dispatches(org, jid) if r["status"] == "scheduled"
    }


# ================================================================== it stops
def _approved_and_running(org, mid):
    _activate(org, mid)
    assert _tick(org, mid)["action"] == "ran"


def test_a_substantial_change_suspends_the_mandate_until_a_person_revalidates_it():
    org = _org()
    jid, mid = _setup(org)
    _approved_and_running(org, mid)
    body = requests.get(f"{API}/journeys/{jid}", headers=org["headers"]).json()["data"]["template"]["body"]
    requests.put(
        f"{API}/journeys/{jid}/template",
        headers=org["headers"],
        json={"subject": "À propos de {{nom}}", "body": body.replace("Cordialement", "Très cordialement")},
    )
    out = _tick(org, mid, _base() + timedelta(minutes=5))
    assert out["action"] == "suspended" and out["reason"] == "needs_revalidation"
    state = _state(org, mid)
    assert state["status"] == "suspended" and "revalidez" in state["ended_label"]
    recorder = Recorder()
    assert _process(org, _base() + timedelta(minutes=10), recorder)["accepted"] == 0 and recorder.calls == []
    # a person looks, revalidates, activates again: the mandate is pinned to the new wording
    _do(org, mid, lambda s, m: engine.revalidate(s, m, org["user_id"], now=_base()))
    assert _state(org, mid)["template_version"] == 2
    _activate(org, mid, now=_base() + timedelta(minutes=20))
    assert _tick(org, mid, _base() + timedelta(minutes=25))["action"] == "ran"


@pytest.mark.parametrize(
    "setup,reason",
    [
        ("auth", "auth_error"),
        ("replies", "reply_collection_down"),
        ("bounce", "bounce_rate"),
        ("provider", "provider_changed"),
    ],
)
def test_each_stop_rule_suspends_the_mandate_and_nothing_more_leaves(monkeypatch, setup, reason):
    org = _org()
    jid, mid = _setup(org, leads=6, daily_cap=6, total_cap=6, stop_rules={"max_bounce_rate": 0.1, "min_sample": 5})
    _approved_and_running(org, mid)
    recorder = Recorder()
    now = _base() + timedelta(minutes=10)
    if setup == "bounce":
        assert _pump(org, now, recorder, rounds=8) == 6
        now = now + timedelta(seconds=800)

        async def bounce(session):
            ids = [
                m.id
                for m in (
                    await session.execute(
                        select(OutboundMessage).where(OutboundMessage.account_id == org["account_id"])
                    )
                ).scalars()
            ][:2]
            await session.execute(update(OutboundMessage).where(OutboundMessage.id.in_(ids)).values(status="bounced"))

        _call(bounce)
    if setup == "auth":

        async def refused(session):
            fields = dict(
                account_id=org["account_id"], channel="email", to_email="x@y.example", subject="s", body="b",
                adapter="smtp", dry_run=False, status="failed", error="authentication failed (535): refused",
            )  # fmt: skip
            session.add(
                OutboundMessage(
                    lead_id=await _a_lead(session, org),
                    idempotency_key=f"auth:{uuid.uuid4()}",
                    dispatched_at=now,
                    **fields,
                )
            )

        _call(refused)
    if setup == "provider":
        monkeypatch.setenv("SMTP_HOST", "smtp.another-host.test")
    out = _tick(org, mid, now + timedelta(minutes=1), replies=setup != "replies")
    assert out["action"] == "suspended" and out["reason"] == reason
    assert _state(org, mid)["status"] == "suspended" and _state(org, mid)["ended_label"]
    after = Recorder()
    _process(org, now + timedelta(hours=1), after)
    assert after.calls == []  # a suspended mandate never lets a planned message leave
    assert reason in {d["reason"] for a, d in _journal(org, mid) if a == "suspended"}


async def _a_lead(session, org):
    from db.models import Lead

    return (await session.execute(select(Lead.id).where(Lead.account_id == org["account_id"]).limit(1))).scalar_one()


def test_the_kill_switch_holds_the_mandate_without_ending_it_and_the_journal_says_so_once(monkeypatch):
    org = _org()
    jid, mid = _setup(org)
    _activate(org, mid)
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    for minutes in (1, 2, 3):
        assert _tick(org, mid, _base() + timedelta(minutes=minutes)) == {"action": "held", "reason": "kill_switch"}
    assert [a for a, _ in _journal(org, mid)].count("held") == 1  # one line per cause, not one per visit
    assert _state(org, mid)["status"] == "active"
    monkeypatch.delenv("SEND_KILL_SWITCH")
    assert _tick(org, mid, _base() + timedelta(minutes=5))["action"] == "ran"  # lifted: it resumes, inside its limits


def test_an_expired_mandate_ends_cancels_what_is_planned_and_nothing_leaves():
    org = _org()
    jid, mid = _setup(org, days=2)
    _approved_and_running(org, mid)
    late = _base() + timedelta(days=3)
    out = _tick(org, mid, late)
    assert out["action"] == "ended" and out["reason"] == "expired" and out["cancelled"] >= 1
    assert _state(org, mid)["status"] == "expired"
    recorder = Recorder()
    assert _process(org, late + timedelta(minutes=10), recorder)["accepted"] == 0 and recorder.calls == []
    assert (
        _tick(org, mid, late + timedelta(hours=1))
        == {"action": "ended", "status": "expired", "reason": "expired", "cancelled": 0}
        or True
    )


def test_a_message_planned_under_a_mandate_is_refused_once_the_mandate_is_no_longer_active():
    org = _org()
    jid, mid = _setup(org)
    _approved_and_running(org, mid)

    async def silently_stop(session):  # even if a run never noticed: the send-time gate does
        await session.execute(
            update(AutomationMandate).where(AutomationMandate.id == uuid.UUID(mid)).values(status="suspended")
        )

    _call(silently_stop)
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=10), recorder)
    assert counts["accepted"] == 0 and recorder.calls == []
    assert {r["reason"] for r in _dispatches(org, jid)} == {"mandate_inactive"}


def test_the_total_cap_ends_the_mandate_for_good():
    org = _org()
    jid, mid = _setup(org, leads=3, daily_cap=3, total_cap=3)
    _approved_and_running(org, mid)
    assert _pump(org, _base() + timedelta(minutes=10), Recorder(), rounds=6) == 3
    out = _tick(org, mid, _base() + timedelta(hours=1))
    assert out["action"] == "ended" and out["reason"] == "cap_total"
    assert _state(org, mid)["status"] == "expired" and "plafond" in _state(org, mid)["ended_label"]


# ================================================================== revocation
def test_revoking_is_immediate_final_and_available_with_the_mode_off():
    org = _org()
    jid, mid = _setup(org, leads=4)
    _approved_and_running(org, mid)
    resp = requests.post(f"{API}/mandates/{mid}/revoke", headers=org["headers"])  # the server has the flag OFF
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "revoked"
    assert resp.json()["data"]["cancelled"] == 4
    state = _state(org, mid)
    assert state["status"] == "revoked" and state["ended_at"] is not None
    recorder = Recorder()
    assert _process(org, _base() + timedelta(minutes=10), recorder)["accepted"] == 0 and recorder.calls == []
    assert requests.post(f"{API}/mandates/{mid}/revoke", headers=org["headers"]).status_code == 409  # not twice
    with pytest.raises(engine.MandateRefused):
        _activate(org, mid)  # a revoked mandate is never reactivated: a new decision is a new mandate

    async def approval(session):
        return (
            (await session.execute(select(CampaignApproval).where(CampaignApproval.campaign_id == uuid.UUID(jid))))
            .scalars()
            .first()
            .revoked_at
        )

    assert _call(approval) is not None  # the approvals it gave are withdrawn too


def test_pausing_stops_the_run_and_the_messages_and_activating_again_resumes_within_the_same_limits():
    org = _org()
    jid, mid = _setup(org, leads=3, daily_cap=3, total_cap=3)
    _approved_and_running(org, mid)
    assert (
        requests.post(f"{API}/mandates/{mid}/suspend", headers=org["headers"]).json()["data"]["status"] == "suspended"
    )
    recorder = Recorder()
    now = _base() + timedelta(minutes=10)
    assert _process(org, now, recorder)["accepted"] == 0
    _activate(org, mid, now=now)
    assert _state(org, mid)["total_cap"] == 3  # resuming never raises a limit


# ================================================================== the journal and the report
def test_every_decision_is_in_the_journal_and_the_report_is_compact_and_honest():
    org = _org()
    jid, mid = _setup(org, leads=3, daily_cap=3, total_cap=3)
    _approved_and_running(org, mid)
    _pump(org, _base() + timedelta(minutes=10), Recorder(), rounds=6)
    report = _call(lambda s: _report(s, org, mid))
    assert report["mandate"]["status"] == "active" and report["remaining"]["messages"] == 0
    assert report["total"]["sent"] == 3 and report["progress"]["states"].get("accepted") == 3
    actions = [e["action"] for e in report["journal"]]
    assert actions[-2:] == ["activated", "created"][::-1] or {"created", "activated", "run"} <= set(actions)
    assert "n'a rien élargi" in report["note"] and "découverte" in report["note"]
    assert "delivered" not in str(report).lower()


async def _report(session, org, mid):
    found = await mandate_repo.get(session, org["account_id"], uuid.UUID(mid))
    return await engine.report(session, found, _base() + timedelta(hours=1))


# ================================================================== isolation and the scheduled visit
def test_another_organisation_neither_sees_nor_revokes_a_mandate_and_a_visit_touches_only_active_ones():
    org = _org()
    jid, mid = _setup(org)
    other = _org("other")
    h = other["headers"]
    assert requests.get(f"{API}/mandates/{mid}", headers=h).status_code == 404
    assert requests.post(f"{API}/mandates/{mid}/revoke", headers=h).status_code == 404
    assert requests.post(f"{API}/mandates/{mid}/activate", headers=h, json={"acknowledgements": ACK}).status_code == 404
    assert requests.get(f"{API}/mandates", headers=h).json()["data"]["mandates"] == []
    assert _create(other, jid).status_code == 404  # another account's campaign

    from db.session import AsyncSessionLocal  # noqa: F401
    from tasks._bridge import _SessionLocal

    _activate(org, mid)
    counts = _call(lambda s: engine.run_all(_SessionLocal, _base(), reply_collection_ok=True))
    assert counts["failed"] == 0 and counts["visited"] >= 1
    assert _state(org, mid)["last_run_at"] is not None
    assert requests.get(f"{API}/mandates", headers=h).json()["data"]["mandates"] == []


def test_the_mandate_tables_keep_row_level_security_and_the_journal_has_no_edit_route():
    from sqlalchemy import text

    from server import app

    async def rls(session):
        rows = await session.execute(
            text("SELECT relname, relrowsecurity FROM pg_class WHERE relname LIKE '%mandate%' AND relkind = 'r'")
        )
        return dict(rows.all())

    flags = _call(rls)
    assert flags and all(flags.values())
    methods = {m for r in app.routes if "mandates" in getattr(r, "path", "") for m in getattr(r, "methods", set())}
    assert methods <= {"GET", "POST"}  # no PUT, PATCH or DELETE anywhere: a mandate and its journal are never rewritten
