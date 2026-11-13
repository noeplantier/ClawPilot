"""Credits and outreach models: pure rules, no server, no network."""

from datetime import datetime, timedelta, timezone

from services.outreach_os import credits

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)  # 10:00 in Paris
LIMITS = credits.Limits(per_day=10, per_session=4)


def test_the_template_model_costs_nothing_and_calls_no_ai():
    gabarit = credits.model("gabarit")
    assert gabarit.credits == 0 and gabarit.uses_ai is False
    assert credits.check(credits.windows([(T0, 4)], T0, LIMITS), 0, T0) is None  # 0 always fits, even when exhausted


def test_an_unknown_model_is_the_default_one():
    assert credits.model("nope").id == credits.DEFAULT_MODEL
    assert credits.model(None).id == credits.DEFAULT_MODEL
    assert [m.credits for m in credits.MODELS] == sorted(m.credits for m in credits.MODELS)  # cheapest first


def test_nothing_spent_means_empty_windows_with_no_reset():
    session, day = credits.windows([], T0, LIMITS)
    assert (session.used, session.remaining, session.resets_at) == (0, 4, None)
    assert (day.used, day.remaining, day.resets_at) == (0, 10, None)


def test_a_session_lasts_five_hours_from_its_first_spend():
    spends = [(T0, 1), (T0 + timedelta(hours=1), 2)]
    session, day = credits.windows(spends, T0 + timedelta(hours=2), LIMITS)
    assert session.used == 3 and session.resets_at == T0 + timedelta(hours=5)
    later, day_later = credits.windows(spends, T0 + timedelta(hours=6), LIMITS)
    assert later.used == 0 and later.resets_at is None  # the session is over: a new one starts with the next spend
    assert day_later.used == 3  # the day still counts it


def test_a_spend_after_the_session_starts_a_new_one():
    spends = [(T0, 3), (T0 + timedelta(hours=5, minutes=1), 1)]
    session, _ = credits.windows(spends, T0 + timedelta(hours=6), LIMITS)
    assert session.used == 1 and session.resets_at == T0 + timedelta(hours=10, minutes=1)


def test_the_day_is_the_paris_day():
    yesterday_paris = datetime(2026, 11, 12, 22, 30, tzinfo=timezone.utc)  # 23:30 in Paris, the 12th
    after_midnight = datetime(2026, 11, 12, 23, 30, tzinfo=timezone.utc)  # 00:30 in Paris, the 13th
    _, day = credits.windows([(yesterday_paris, 5), (after_midnight, 1)], T0, LIMITS)
    assert day.used == 1
    assert day.resets_at == datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)  # midnight in Paris


def test_a_spend_over_a_window_is_refused_with_its_reset():
    current = credits.windows([(T0, 3)], T0 + timedelta(minutes=5), LIMITS)
    assert credits.check(current, 1, T0) is None
    refused = credits.check(current, 2, T0)
    assert refused is not None and refused.code == "credits_exhausted" and refused.window == "session"
    assert refused.resets_at == T0 + timedelta(hours=5)
    assert "15:00" in refused.message  # 14:00 UTC is 15:00 in Paris


def test_a_cost_over_an_empty_window_names_the_setting():
    refused = credits.check(credits.windows([], T0, credits.Limits(per_day=10, per_session=1)), 2, T0)
    assert refused is not None and "CREDITS_PER_SESSION" in refused.message


def test_limits_read_from_the_environment_with_safe_defaults():
    assert credits.limits_from({}) == credits.Limits(credits.DEFAULT_PER_DAY, credits.DEFAULT_PER_SESSION)
    assert credits.limits_from({"CREDITS_PER_DAY": "40", "CREDITS_PER_SESSION": "x"}) == credits.Limits(40, 30)
    assert credits.limits_from({"CREDITS_PER_DAY": "-1"}).per_day == credits.DEFAULT_PER_DAY
