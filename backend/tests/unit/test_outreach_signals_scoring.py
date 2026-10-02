"""Signals (three states) and the explainable score — pure and deterministic."""

from datetime import date

import pytest
from pydantic import ValidationError

from services.outreach_os import signals as sig
from services.outreach_os.scoring import DEFAULT_WEIGHTS, ScoreConfig, compute_score
from services.outreach_os.types import RawListing, SignalResult, SignalState, SiteSnapshot

NOW = date(2026, 6, 1)
OK_HTML = (
    '<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>'
    "<body>Réserver</body></html>"
)


def listing(**kw):
    base = dict(external_id="1", name="Chez Test", source_name="annuaire", source_url="u")
    return RawListing(**{**base, **kw})


def run(lst, snap=None, **kw):
    return {r.key: r for r in sig.analyze(lst, snap, now=NOW, **kw)}


def snapshot(status=200, html=OK_HTML, error=None):
    return SiteSnapshot(url="https://t.example", status=status, html=html, error=error)


# ---- every signal returns a result, in a stable order -------------------------------------------
def test_analyze_returns_all_signals_in_order():
    assert tuple(sig.analyze(listing(), None, now=NOW)[i].key for i in range(7)) == sig.ALL_SIGNALS


# ---- no_website ---------------------------------------------------------------------------------
def test_no_website_states():
    assert run(listing())[sig.NO_WEBSITE].state is SignalState.DETECTED
    third = run(listing(website="https://facebook.com/x"))[sig.NO_WEBSITE]
    assert third.state is SignalState.DETECTED and "facebook.com" in third.evidence
    assert run(listing(website="https://t.example"))[sig.NO_WEBSITE].state is SignalState.NOT_DETECTED


# ---- unreachable: unknown when not applicable or not checked, never "detected" by default ----------
def test_unreachable_states():
    site = listing(website="https://t.example")
    assert run(listing())[sig.WEBSITE_UNREACHABLE].state is SignalState.UNKNOWN  # no website: not applicable
    assert run(site, None)[sig.WEBSITE_UNREACHABLE].state is SignalState.UNKNOWN  # not checked
    assert (
        run(site, snapshot(status=503, html=None, error="boom"))[sig.WEBSITE_UNREACHABLE].state is SignalState.DETECTED
    )
    assert (
        run(site, snapshot(status=None, html=None, error="timeout"))[sig.WEBSITE_UNREACHABLE].state
        is SignalState.DETECTED
    )
    assert run(site, snapshot())[sig.WEBSITE_UNREACHABLE].state is SignalState.NOT_DETECTED


# ---- booking / mobile need HTML; without it they are UNKNOWN ---------------------------------------
def test_html_dependent_signals_are_unknown_without_html():
    site = listing(website="https://t.example")
    for snap in (None, snapshot(status=503, html=None), snapshot(html="")):
        r = run(site, snap)
        assert r[sig.BOOKING_PAGE_MISSING].state is SignalState.UNKNOWN
        assert r[sig.NOT_MOBILE_FRIENDLY].state is SignalState.UNKNOWN


def test_booking_and_mobile_detection():
    site = listing(website="https://t.example")
    good = run(site, snapshot())
    assert good[sig.BOOKING_PAGE_MISSING].state is SignalState.NOT_DETECTED
    assert good[sig.NOT_MOBILE_FRIENDLY].state is SignalState.NOT_DETECTED
    bare = run(site, snapshot(html="<html><body>Bienvenue</body></html>"))
    assert bare[sig.BOOKING_PAGE_MISSING].state is SignalState.DETECTED
    assert "homepage" in bare[sig.BOOKING_PAGE_MISSING].evidence  # states the limit of the check
    assert bare[sig.NOT_MOBILE_FRIENDLY].state is SignalState.DETECTED
    assert "heuristic" in bare[sig.NOT_MOBILE_FRIENDLY].evidence
    fixed = run(site, snapshot(html='<meta name="viewport" content="width=1024">'))
    assert fixed[sig.NOT_MOBILE_FRIENDLY].state is SignalState.DETECTED  # viewport present but not responsive


def test_mobile_analyzer_is_injectable_and_can_abstain():
    class Abstain:
        def is_mobile_friendly(self, html):
            return None

    r = run(listing(website="https://t.example"), snapshot(), mobile_analyzer=Abstain())
    assert r[sig.NOT_MOBILE_FRIENDLY].state is SignalState.UNKNOWN


# ---- contact, staleness, completeness ----------------------------------------------------------------
def test_contact_signal():
    assert run(listing(phone="0478123456"))[sig.PUBLIC_CONTACT_PRESENT].state is SignalState.DETECTED
    assert run(listing(email="a@b.example"))[sig.PUBLIC_CONTACT_PRESENT].state is SignalState.DETECTED
    assert run(listing())[sig.PUBLIC_CONTACT_PRESENT].state is SignalState.NOT_DETECTED


def test_stale_listing_boundaries():
    assert run(listing())[sig.STALE_LISTING].state is SignalState.UNKNOWN  # no date: never assumed stale
    exactly = date.fromordinal(NOW.toordinal() - 365)
    assert run(listing(last_updated=exactly))[sig.STALE_LISTING].state is SignalState.NOT_DETECTED  # 365d, not > 365
    older = date.fromordinal(NOW.toordinal() - 366)
    assert run(listing(last_updated=older))[sig.STALE_LISTING].state is SignalState.DETECTED
    assert run(listing(last_updated=older), stale_days=400)[sig.STALE_LISTING].state is SignalState.NOT_DETECTED


def test_incomplete_listing_threshold():
    full = listing(phone="1", address="a", hours="h", description="d", website="https://t.example")
    assert run(full)[sig.INCOMPLETE_LISTING].state is SignalState.NOT_DETECTED
    one_missing = listing(phone="1", address="a", hours="h", website="https://t.example")
    assert run(one_missing)[sig.INCOMPLETE_LISTING].state is SignalState.NOT_DETECTED
    two_missing = listing(phone="1", address="a", website="https://t.example")
    assert run(two_missing)[sig.INCOMPLETE_LISTING].state is SignalState.DETECTED
    assert "absent from this source only" in run(two_missing)[sig.INCOMPLETE_LISTING].evidence


# ---- score ----------------------------------------------------------------------------------------------
def results(**states):
    return [SignalResult(k, SignalState(states.get(k, "unknown")), "e") for k in sig.ALL_SIGNALS]


def test_score_all_unknown_is_zero_with_zero_coverage():
    s = compute_score(results(), ScoreConfig())
    assert s.score == 0 and s.coverage == 0.0
    assert all(line.points == 0 for line in s.lines)


def test_score_unknown_and_not_detected_never_contribute():
    s = compute_score(results(**{sig.NO_WEBSITE: "not_detected"}), ScoreConfig())
    assert s.score == 0 and s.coverage == round(1 / 7, 2)


def test_score_counts_only_detected_with_points_per_signal():
    s = compute_score(results(**{sig.NO_WEBSITE: "detected", sig.STALE_LISTING: "detected"}), ScoreConfig())
    assert s.score == DEFAULT_WEIGHTS[sig.NO_WEBSITE] + DEFAULT_WEIGHTS[sig.STALE_LISTING]
    assert {ln.signal: ln.points for ln in s.lines if ln.points} == {sig.NO_WEBSITE: 30, sig.STALE_LISTING: 10}
    assert s.to_breakdown()[0]["explanation"] == "e"


def test_score_is_clamped_to_0_100():
    everything = compute_score(results(**{k: "detected" for k in sig.ALL_SIGNALS}), ScoreConfig())
    assert everything.score == 100  # raw sum is 120
    negative = ScoreConfig(weights={sig.NO_WEBSITE: -50})
    assert compute_score(results(**{sig.NO_WEBSITE: "detected"}), negative).score == 0


def test_score_config_is_configurable_and_recomputable():
    base = results(**{sig.NO_WEBSITE: "detected"})
    heavier = ScoreConfig(weights={**DEFAULT_WEIGHTS, sig.NO_WEBSITE: 60})
    assert compute_score(base, ScoreConfig()).score == 30
    assert compute_score(base, heavier).score == 60
    assert compute_score(base, heavier) == compute_score(base, heavier)  # deterministic


def test_config_hash_ignores_label_and_changes_with_weights():
    a, b = ScoreConfig(label="a"), ScoreConfig(label="b")
    assert a.config_hash == b.config_hash
    assert a.config_hash != ScoreConfig(weights={**DEFAULT_WEIGHTS, sig.NO_WEBSITE: 31}).config_hash
    assert a.config_hash != ScoreConfig(stale_days=200).config_hash


@pytest.mark.parametrize(
    "bad",
    [
        {"weights": {"made_up_signal": 5}},
        {"weights": {sig.NO_WEBSITE: 101}},
        {"weights": {sig.NO_WEBSITE: -101}},
        {"stale_days": 5},
    ],
)
def test_config_validation_rejects_bad_input(bad):
    with pytest.raises(ValidationError):
        ScoreConfig(**bad)


def test_empty_weights_scores_zero_with_full_coverage():
    s = compute_score(results(**{sig.NO_WEBSITE: "detected"}), ScoreConfig(weights={}))
    assert s.score == 0 and s.coverage == 1.0
