"""The bounded automatic mode as pure rules: what a mandate may be, when it acts, waits or stops, and what each of its
messages must satisfy at the moment it leaves. Offline, no database."""

from datetime import datetime, timedelta, timezone

import pytest

from services.outreach_os import campaign_template as ct
from services.outreach_os import mandate as m

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)
ZONE = {"south": 45.70, "west": 4.78, "north": 45.80, "east": 4.90, "category": "restaurants"}


def spec(**over):
    base = dict(zones=[ZONE], daily_cap=20, total_cap=100, expires_at=NOW + timedelta(days=14))
    return m.Spec(**{**base, **over})


def codes(found):
    return {p.code for p in found}


# ---------------------------------------------------------------- a mandate as written
def test_a_bounded_mandate_is_acceptable():
    assert m.problems(spec(), NOW) == []
    assert m.problems(spec(daily_cap=1, total_cap=1, ai_budget=0), NOW) == []


@pytest.mark.parametrize(
    "over,code",
    [
        ({"zones": []}, "zone_missing"),
        ({"zones": [ZONE, ZONE]}, "too_many_zones"),
        ({"daily_cap": 0}, "daily_cap"),
        ({"daily_cap": m.MAX_DAILY + 1, "total_cap": m.MAX_TOTAL}, "daily_cap"),
        ({"total_cap": 0, "daily_cap": 1}, "total_cap"),
        ({"total_cap": m.MAX_TOTAL + 1}, "total_cap"),
        ({"daily_cap": 50, "total_cap": 10}, "caps_order"),
        ({"expires_at": NOW}, "expiry_past"),
        ({"expires_at": NOW + timedelta(days=m.MAX_DAYS + 1)}, "expiry_far"),
        ({"window_start_hour": 18, "window_end_hour": 8}, "window"),
        ({"min_delay_seconds": 5}, "cadence"),
        ({"search_every_hours": 1}, "search_frequency"),
        ({"ai_budget": -1}, "ai_budget"),
    ],
)
def test_an_unbounded_or_incoherent_mandate_is_refused_with_the_reason(over, code):
    assert code in codes(m.problems(spec(**over), NOW))


def test_a_mandate_has_no_unlimited_form():
    # every limit has an upper bound: there is no "no cap", "no expiry" or "all zones" value to ask for
    assert m.MAX_DAILY <= m.MAX_TOTAL and m.MAX_DAYS <= 90 and m.MAX_ZONES == 1
    assert codes(m.problems(spec(total_cap=10**9), NOW)) >= {"total_cap"}


def test_the_stop_rules_can_be_stricter_never_looser_than_the_hard_limits():
    assert m.stop_rules_of(None) == m.DEFAULT_STOP_RULES
    stricter = m.stop_rules_of({"max_bounce_rate": 0.01, "max_opt_out_rate": 0.02, "min_sample": 10})
    assert (stricter["max_bounce_rate"], stricter["max_opt_out_rate"], stricter["min_sample"]) == (0.01, 0.02, 10)
    looser = m.stop_rules_of({"max_bounce_rate": 0.9, "max_opt_out_rate": 0.9, "min_sample": 100000})
    assert looser["max_bounce_rate"] == 0.10 and looser["max_opt_out_rate"] == 0.20 and looser["min_sample"] == 200
    assert m.stop_rules_of({"max_bounce_rate": 0})["max_bounce_rate"] == 0.005  # not zero: a rate of 0 stops at once


# ---------------------------------------------------------------- may it act now
PINNED = m.Pinned(
    content_hash="c1", zone_hash="z1", offer_hash="o1", sender_fp="s1", provider="smtp (smtp.mailhost.test)"
)


def health(**over):
    base = dict(
        now=NOW, kill_switch=False, feature_enabled=True, auth_error=False, reply_collection_ok=True, sent_total=0,
        bounced=0, opted_out=0, current=ct.Current("c1", "z1", "o1", "s1"), provider=PINNED.provider,
    )  # fmt: skip
    return m.Health(**{**base, **over})


def decide(status="active", expires=NOW + timedelta(days=5), total_cap=100, rules=None, **over):
    return m.verdict(
        status=status, expires_at=expires, total_cap=total_cap, rules=rules or {}, pinned=PINNED, health=health(**over)
    )


def test_a_healthy_active_mandate_may_act():
    assert decide() == m.GO


@pytest.mark.parametrize(
    "kwargs,action,code",
    [
        ({"status": "revoked"}, "end", "revoked"),
        ({"status": "expired"}, "end", "expired"),
        ({"status": "draft"}, "hold", "not_active"),
        ({"status": "suspended"}, "hold", "not_active"),
        ({"feature_enabled": False}, "hold", "feature_disabled"),
        ({"expires": NOW}, "end", "expired"),
        ({"kill_switch": True}, "hold", "kill_switch"),
        ({"auth_error": True}, "suspend", "auth_error"),
        ({"reply_collection_ok": False}, "suspend", "reply_collection_down"),
        ({"provider": "sendgrid"}, "suspend", "provider_changed"),
        ({"sent_total": 100, "total_cap": 100}, "end", "cap_total"),
    ],
)
def test_each_stop_condition_gives_its_verdict_and_a_sentence(kwargs, action, code):
    got = decide(**kwargs)
    assert (got.action, got.code) == (action, code)
    assert got.label


@pytest.mark.parametrize(
    "current,changed",
    [
        (ct.Current("c2", "z1", "o1", "s1"), "template_changed"),
        (ct.Current("c1", "z2", "o1", "s1"), "zone_changed"),
        (ct.Current("c1", "z1", "o2", "s1"), "offer_changed"),
        (ct.Current("c1", "z1", "o1", "s2"), "sender_changed"),
    ],
)
def test_a_substantial_change_suspends_the_mandate_until_it_is_revalidated(current, changed):
    got = decide(current=current)
    assert (got.action, got.code) == ("suspend", "needs_revalidation") and changed in (got.detail or "")


def test_a_rate_means_nothing_on_a_handful_of_messages_then_stops_the_mandate():
    assert decide(sent_total=10, bounced=5) == m.GO  # below the sample of 20: no verdict from 5 bounces out of 10
    assert decide(sent_total=21, bounced=1) == m.GO  # 4.8 %, under the 5 % limit
    assert decide(sent_total=20, bounced=1).code == "bounce_rate"  # 5 % exactly: at or above the limit stops
    stopped = decide(sent_total=40, bounced=3)  # 7.5 %
    assert (stopped.action, stopped.code, stopped.detail) == ("suspend", "bounce_rate", "3/40")
    opposed = decide(sent_total=40, opted_out=5)  # 12.5 % against a 10 % limit
    assert (opposed.action, opposed.code) == ("suspend", "opt_out_rate")


def test_a_stricter_rule_set_by_the_person_is_respected():
    assert decide(sent_total=40, bounced=1, rules={"max_bounce_rate": 0.02, "min_sample": 20}).code == "bounce_rate"


def test_the_order_of_checks_reports_the_cause_a_person_needs_first():
    # the kill switch is reported before anything else about a running mandate; expiry before it
    assert decide(kill_switch=True, auth_error=True).code == "kill_switch"
    assert decide(auth_error=True, reply_collection_ok=False).code == "auth_error"
    assert decide(expires=NOW, kill_switch=True).code == "expired"


def test_the_fixed_stops_are_not_configurable():
    assert {"kill_switch", "auth_error", "reply_collection_down", "needs_revalidation", "expired", "cap_total"} <= set(
        m.FIXED_STOPS
    )
    assert not set(m.stop_rules_of({"auth_error": False, "kill_switch": False})) & set(m.FIXED_STOPS)


# ---------------------------------------------------------------- the moment a message leaves
def refuse(**over):
    base = dict(
        status="active", expires_at=NOW + timedelta(days=1), now=NOW, window_start_hour=8, window_end_hour=18,
        local_hour=10, min_delay_seconds=60, seconds_since_last=None,
    )  # fmt: skip
    return m.send_refusal(**{**base, **over})


def test_a_message_of_an_active_mandate_inside_its_window_may_leave():
    assert refuse() is None
    assert refuse(seconds_since_last=61) is None


@pytest.mark.parametrize(
    "over,code",
    [
        ({"status": "suspended"}, "mandate_inactive"),
        ({"status": "revoked"}, "mandate_inactive"),
        ({"expires_at": NOW}, "expired"),
        ({"local_hour": 7}, "outside_window"),
        ({"local_hour": 18}, "outside_window"),
    ],
)
def test_a_message_never_leaves_outside_its_mandate(over, code):
    assert refuse(**over)[0] == code


def test_the_mandates_own_cadence_makes_a_message_wait_for_exactly_the_missing_time():
    code, retry = refuse(seconds_since_last=20)
    assert code == "limit_delay" and retry == NOW + timedelta(seconds=40)
