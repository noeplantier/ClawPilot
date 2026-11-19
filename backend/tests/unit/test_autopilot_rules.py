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


class _P:
    def __init__(self, phone=None, email=None, website=None):
        self.phone, self.email, self.website = phone, email, website


def test_a_place_is_added_when_a_person_could_reach_it_and_a_homepage_is_read_only_within_the_cap():
    with_mail = [_P("+33 1", "a@x.fr") for _ in range(3)]
    with_site = [_P("+33 1", None, f"https://s{i}.fr") for i in range(ap.SITES_PER_RUN + 4)]
    no_phone = [_P(None, "b@x.fr", "https://b.fr"), _P(None, None, None)]
    read, as_published, later = ap.plan_additions(with_site + with_mail + no_phone)
    assert len(read) == ap.SITES_PER_RUN and all(p.website for p in read)  # at most SITES_PER_RUN homepages per run
    assert as_published == with_mail  # a phone and an e-mail: added as published
    assert later == 4  # a site-only place past the cap waits for the next run, counted, never dropped silently
    assert not {id(p) for p in no_phone} & {id(p) for p in read + as_published}  # no phone: never added


def test_a_place_with_mail_and_site_has_its_homepage_read_and_the_total_is_capped():
    both = _P("+33 1", "a@x.fr", "https://a.fr")
    read, as_published, later = ap.plan_additions([both])
    assert (read, as_published, later) == ([both], [], 0)
    many = [_P("+33 1", f"m{i}@x.fr") for i in range(ap.MAX_PLACES_PER_RUN + 10)]
    assert len(ap.plan_additions(many)[1]) == ap.MAX_PLACES_PER_RUN
