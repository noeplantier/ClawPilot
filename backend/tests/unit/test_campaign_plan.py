"""The pure rules of an individual campaign: review blockers, schedule, honest tracking states."""

from datetime import datetime, timedelta, timezone

import pytest

from services.outreach_os import campaign_plan as cp

UTC = timezone.utc
POLICY = cp.SlotPolicy(
    max_per_day=20, max_per_hour=100, min_delay_seconds=60, window_start_hour=8, window_end_hour=18, timezone="UTC"
)


def test_unresolved_variables_are_found_in_every_common_syntax():
    text = "Bonjour {{name}}, {ville}, %NAME%, [[x]], <<y>>, [Ville], [Nom]"
    assert cp.unresolved_variables(text) == ["{{name}}", "{ville}", "%NAME%", "[[x]]", "<<y>>", "[Ville]", "[Nom]"]
    assert (
        cp.unresolved_variables("Bonjour, je vous écris au sujet de Chez Alice (Lyon).", "À propos de Chez Alice") == []
    )
    assert cp.unresolved_variables("{{a}} et {{a}}") == ["{{a}}"]  # once each


def _item(**over):
    base = dict(
        subject="À propos de Chez Alice",
        body="Bonjour, un message sérieux.\n\nOrigine de vos données : annuaire.",
        facts=("Sur la page d'accueil, pas de réservation.",),
        sourced_now=("Sur la page d'accueil, pas de réservation.",),
        compliance=(),
        sender_configured=True,
    )
    base.update(over)
    return cp.ReviewInput(**base)


def test_a_clean_draft_has_no_blocker_and_an_edited_one_is_flagged_but_not_blocked():
    assert cp.review_problems(_item()) == []
    flagged = cp.review_problems(_item(edited_by_hand=True))
    assert [p.code for p in flagged] == ["edited_by_hand"] and cp.blocking(flagged) == []


def test_every_blocker_of_the_review_is_named():
    cases = {
        "empty_subject": _item(subject="  "),
        "empty_body": _item(body=""),
        "unresolved_variable": _item(body="Bonjour {{name}}"),
        "unsourced_fact": _item(sourced_now=()),  # the signal was dismissed since the draft was written
        "sender_missing": _item(sender_configured=False),
        "not_compliant": _item(compliance=("missing working unsubscribe link",)),
    }
    for code, item in cases.items():
        found = cp.review_problems(item)
        assert code in [p.code for p in cp.blocking(found)], code
    unsourced = cp.review_problems(_item(sourced_now=()))[0]
    assert "Sur la page d'accueil" in unsourced.label  # the reviewer sees which statement lost its source


def test_a_draft_without_any_fact_is_fine_nothing_is_required_to_be_invented():
    assert cp.review_problems(_item(facts=(), sourced_now=())) == []


def test_every_refusal_has_a_kind_and_an_unknown_code_stops_the_message():
    for code, (kind, label) in cp.SEND_REFUSALS.items():
        assert kind in ("wait", "stop") and label, code
    assert cp.refusal_kind("limit_daily") == "wait" and cp.refusal_kind("suppressed") == "stop"
    assert cp.refusal_kind("something_new") == "stop"  # fail closed
    assert cp.exclusion_label("provider_requires_opt_in").startswith("Pas d'opt-in")


def test_two_prospects_with_the_same_folded_name_in_the_same_city_are_one_establishment():
    assert cp.establishment_key("Restaurant Chez Alice", "Lyon") == cp.establishment_key("chez  ALICE", "lyon")
    assert cp.establishment_key("Chez Alice", "Lyon") != cp.establishment_key("Chez Alice", "Paris")


# ------------------------------------------------------------------------------------------------ schedule
def _local(slot, tz="UTC"):
    import zoneinfo

    return slot.astimezone(zoneinfo.ZoneInfo(tz))


def test_one_hundred_messages_become_five_days_of_twenty_inside_the_window_a_minute_apart():
    now = datetime(2026, 11, 9, 7, 0, tzinfo=UTC)  # a Monday, before the window opens
    slots = cp.plan_slots(100, now=now, policy=POLICY, already_sent=[])
    assert len(slots) == 100
    assert slots[0] == datetime(2026, 11, 9, 8, 0, tzinfo=UTC)  # the window opens at 08:00: nothing earlier
    assert all(8 <= s.hour < 18 for s in slots)
    assert all(b - a >= timedelta(seconds=60) for a, b in zip(slots, slots[1:]))
    summary = cp.schedule_summary(slots, "UTC")
    assert [d["count"] for d in summary["days"]] == [20, 20, 20, 20, 20]
    assert summary["first_at"] == slots[0] and summary["last_at"] == slots[-1]


def test_what_already_left_today_counts_against_the_daily_cap():
    now = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
    sent = [now - timedelta(minutes=i + 1) for i in range(15)]
    slots = cp.plan_slots(10, now=now, policy=POLICY, already_sent=sent)
    today = [s for s in slots if s.date() == now.date()]
    assert len(today) == 5  # 15 already left: 5 are left for today, the rest start tomorrow
    assert slots[5].date() == (now + timedelta(days=1)).date() and slots[5].hour == 8


def test_the_rolling_hourly_cap_spaces_the_messages_out():
    policy = cp.SlotPolicy(1000, 3, 1, 8, 18, "UTC")
    slots = cp.plan_slots(7, now=datetime(2026, 11, 9, 9, 0, tzinfo=UTC), policy=policy, already_sent=[])
    for slot in slots:
        assert len([x for x in slots if slot - timedelta(hours=1) < x <= slot]) <= 3


def test_the_window_is_read_in_the_organisation_timezone():
    policy = cp.SlotPolicy(20, 100, 60, 8, 18, "Europe/Paris")
    now = datetime(2026, 11, 9, 6, 0, tzinfo=UTC)  # 07:00 in Paris
    slots = cp.plan_slots(3, now=now, policy=policy, already_sent=[])
    assert _local(slots[0], "Europe/Paris").hour == 8 and slots[0] == datetime(2026, 11, 9, 7, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "policy",
    [
        cp.SlotPolicy(0, 100, 60, 8, 18, "UTC"),
        cp.SlotPolicy(20, 0, 60, 8, 18, "UTC"),
        cp.SlotPolicy(20, 100, 60, 18, 8, "UTC"),
        cp.SlotPolicy(20, 100, 60, 9, 9, "UTC"),
    ],
)
def test_a_policy_that_allows_nothing_plans_nothing_instead_of_looping(policy):
    assert cp.plan_slots(10, now=datetime(2026, 11, 9, 9, 0, tzinfo=UTC), policy=policy, already_sent=[]) == []
    assert cp.plan_slots(0, now=datetime(2026, 11, 9, 9, 0, tzinfo=UTC), policy=POLICY, already_sent=[]) == []


# ------------------------------------------------------------------------------------------------ tracking
def test_delivered_does_not_exist_and_a_dry_run_is_never_called_sent():
    assert "delivered" not in cp.TRACKING and not any(
        "livr" in label.lower() and "non prouvée" not in label.lower() for label in cp.TRACKING_LABELS.values()
    )
    state = cp.tracking_state
    assert state(dispatch_status="scheduled", message_status=None, message_dry_run=None, opted_out=False) == "scheduled"
    assert (
        state(dispatch_status="accepted", message_status="sent", message_dry_run=True, opted_out=False) == "simulated"
    )
    assert (
        state(dispatch_status="accepted", message_status="sent", message_dry_run=False, opted_out=False) == "accepted"
    )
    assert (
        state(dispatch_status="accepted", message_status="replied", message_dry_run=False, opted_out=False) == "replied"
    )
    assert (
        state(dispatch_status="accepted", message_status="replied", message_dry_run=False, opted_out=True)
        == "opted_out"
    )
    assert (
        state(dispatch_status="accepted", message_status="bounced", message_dry_run=False, opted_out=False) == "bounced"
    )
    assert (
        state(dispatch_status="accepted", message_status="sending", message_dry_run=False, opted_out=False) == "unknown"
    )
    assert state(dispatch_status="skipped", message_status=None, message_dry_run=None, opted_out=False) == "skipped"
    assert set(cp.TRACKING_LABELS) == set(cp.TRACKING)


def test_each_message_is_read_in_its_own_recipients_window_zone_while_the_daily_cap_counts_in_the_organisation_zone():
    policy = cp.SlotPolicy(20, 100, 60, 8, 18, "UTC")
    now = datetime(2026, 11, 9, 5, 30, tzinfo=UTC)  # 06:30 in Paris (winter, UTC+1), 05:30 in UTC
    paris = cp.plan_slots(2, now=now, policy=policy, already_sent=[], windows=["Europe/Paris", "Europe/Paris"])
    assert paris[0] == datetime(2026, 11, 9, 7, 0, tzinfo=UTC)  # 08:00 in Paris, not 08:00 UTC
    mixed = cp.plan_slots(2, now=now, policy=policy, already_sent=[], windows=["Europe/Paris", "UTC"])
    assert mixed[0] == datetime(2026, 11, 9, 7, 0, tzinfo=UTC)
    assert mixed[1] >= datetime(2026, 11, 9, 8, 0, tzinfo=UTC)  # the second recipient's window opens at 08:00 UTC
    late = datetime(2026, 11, 9, 16, 30, tzinfo=UTC)  # 17:30 in Paris: still inside; 18:00 Paris is the end
    tail = cp.plan_slots(40, now=late, policy=policy, already_sent=[], windows=["Europe/Paris"] * 40)
    assert all(_local(s, "Europe/Paris").hour < 18 for s in tail)
