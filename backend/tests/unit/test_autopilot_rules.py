"""The autopilot's rules: off by default, explicit acknowledgements, bounded numbers, searches never too often."""

from datetime import datetime, timedelta, timezone

import pytest

from services.outreach_os import autopilot as ap

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
ZONE = {"south": 45.75, "west": 4.82, "north": 45.77, "east": 4.86, "category": "bakeries"}
ACKS = list(ap.ACKNOWLEDGEMENTS)


def _on(**over):
    args = dict(
        zone=ZONE, search_every_hours=24, max_approvals=50, drafts=True, acknowledgements=ACKS, user_id="u1", now=NOW
    )
    args.update(over)
    return ap.configure(ap.OFF, **args)


def test_off_by_default_and_an_off_autopilot_does_nothing():
    assert ap.settings_of(None) == ap.OFF and ap.OFF.enabled is False
    p = ap.plan(ap.OFF, NOW)
    assert (p.search, p.approve, p.drafts) == (False, 0, False)


def test_every_acknowledgement_is_required():
    with pytest.raises(ap.Invalid) as refused:
        _on(acknowledgements=ACKS[:3])
    assert refused.value.code == "acknowledgements_required" and "can_stop" in refused.value.label


def test_numbers_are_bounded_and_the_zone_is_checked():
    with pytest.raises(ap.Invalid):
        _on(search_every_hours=1)
    with pytest.raises(ap.Invalid):
        _on(max_approvals=ap.MAX_APPROVALS + 1)
    with pytest.raises(ap.Invalid) as big:
        _on(zone={**ZONE, "north": 46.5})
    assert big.value.code == "zone_too_large"
    with pytest.raises(ap.Invalid) as cat:
        _on(zone={**ZONE, "category": "casinos"})
    assert cat.value.code == "bad_category"


def test_the_first_run_searches_then_waits_for_the_interval():
    s = _on()
    first = ap.plan(s, NOW)
    assert first.search and first.approve == 50 and first.drafts
    after = ap.ran(s, NOW, searched=True)
    assert ap.plan(after, NOW + timedelta(hours=5)).search is False
    assert ap.plan(after, NOW + timedelta(hours=24)).search is True
    assert ap.plan(after, NOW + timedelta(hours=5)).approve == 50  # approvals and drafts run every time


def test_without_a_zone_it_only_approves_and_prepares():
    s = _on(zone=None)
    p = ap.plan(s, NOW)
    assert p.search is False and p.approve == 50 and p.next_search_at is None


def test_the_stored_row_round_trips_and_disabling_keeps_the_settings():
    s = _on()
    assert ap.settings_of(ap.to_row(s)) == s
    off = ap.disable(s)
    assert off.enabled is False and off.zone == s.zone and ap.plan(off, NOW).approve == 0
