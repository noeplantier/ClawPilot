"""Outdated technology, social presence, and reviewer dismissals: pure, on versioned HTML fixtures, no network."""

from datetime import date
from pathlib import Path

from services.outreach_os import signals as sig
from services.outreach_os.scoring import DEFAULT_WEIGHTS, ScoreConfig, compute_score
from services.outreach_os.types import RawListing, SignalResult, SignalState, SiteSnapshot

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "sites"
NOW = date(2026, 10, 3)
LISTING = RawListing("1", "Chez Marcel", "s", "u", website="https://chez-marcel.example", city="Lyon")


def snap(name, status=200):
    html = (FIX / name).read_text() if name else None
    return SiteSnapshot("https://chez-marcel.example", status, html)


def state_of(key, listing=LISTING, snapshot=None):
    return next(r for r in sig.analyze(listing, snapshot, now=NOW, trust_absence=True) if r.key == key)


def test_outdated_markers_are_listed_with_their_evidence():
    r = state_of(sig.OUTDATED_TECHNOLOGY, snapshot=snap("legacy_home.html"))
    assert r.state is SignalState.DETECTED
    assert "jQuery 1.12" in r.evidence and "WordPress 4.9" in r.evidence and "legacy markup (font)" in r.evidence
    assert "homepage" in r.evidence and "other pages not checked" in r.evidence  # the limits are stated


def test_a_modern_homepage_is_not_flagged_and_a_missing_page_is_unknown_not_a_finding():
    assert state_of(sig.OUTDATED_TECHNOLOGY, snapshot=snap("modern_home.html")).state is SignalState.NOT_DETECTED
    assert state_of(sig.OUTDATED_TECHNOLOGY, snapshot=None).state is SignalState.UNKNOWN
    assert state_of(sig.OUTDATED_TECHNOLOGY, snapshot=snap(None, status=503)).state is SignalState.UNKNOWN
    no_site = RawListing("2", "Sans site", "s", "u")
    assert state_of(sig.OUTDATED_TECHNOLOGY, listing=no_site, snapshot=None).state is SignalState.UNKNOWN


def test_social_presence_reads_links_on_the_own_homepage_only():
    linked = state_of(sig.NO_SOCIAL_PRESENCE, snapshot=snap("legacy_home.html"))
    assert (
        linked.state is SignalState.NOT_DETECTED
        and "facebook.com" in linked.evidence
        and "instagram.com" in linked.evidence
    )
    absent = state_of(sig.NO_SOCIAL_PRESENCE, snapshot=snap("modern_home.html"))
    assert absent.state is SignalState.DETECTED and "may exist without being linked" in absent.evidence
    assert state_of(sig.NO_SOCIAL_PRESENCE, snapshot=None).state is SignalState.UNKNOWN


def test_a_listed_social_profile_is_a_presence_not_an_absence():
    profile = RawListing("3", "Chez Paul", "s", "u", website="https://www.facebook.com/chezpaul")
    assert state_of(sig.NO_SOCIAL_PRESENCE, listing=profile).state is SignalState.NOT_DETECTED


def test_the_new_signals_are_weighted_by_default_and_listed_everywhere():
    assert DEFAULT_WEIGHTS[sig.OUTDATED_TECHNOLOGY] == 10 and DEFAULT_WEIGHTS[sig.NO_SOCIAL_PRESENCE] == 5
    assert set(DEFAULT_WEIGHTS) == set(sig.ALL_SIGNALS) == set(sig.SIGNAL_LABELS)


def test_an_older_configuration_without_the_new_keys_still_scores():
    old = ScoreConfig(
        weights={k: v for k, v in DEFAULT_WEIGHTS.items() if k not in (sig.OUTDATED_TECHNOLOGY, sig.NO_SOCIAL_PRESENCE)}
    )
    results = sig.analyze(LISTING, snap("legacy_home.html"), now=NOW)
    new = compute_score(results, ScoreConfig())
    assert compute_score(results, old).score <= new.score  # the new signals simply carry no weight in the old version


def test_a_dismissal_turns_a_finding_into_unknown_and_keeps_the_original_visible():
    results = [
        SignalResult("a", SignalState.DETECTED, "ev"),
        SignalResult("b", SignalState.NOT_DETECTED, "ev2"),
        SignalResult("c", SignalState.UNKNOWN, "ev3"),
    ]
    out = {r.key: r for r in sig.apply_dismissals(results, {"a": "the shop has a site", "b": "x", "c": "y"})}
    assert (
        out["a"].state is SignalState.UNKNOWN
        and "the shop has a site" in out["a"].evidence
        and "Observed: detected" in out["a"].evidence
    )
    assert out["b"].state is SignalState.UNKNOWN  # never turned into a verdict the other way either
    assert out["c"].evidence == "ev3"  # already unknown: untouched
    assert sig.apply_dismissals(results, {}) == results


def test_a_dismissed_signal_no_longer_adds_points():
    detected = [SignalResult(sig.NO_WEBSITE, SignalState.DETECTED, "ev")]
    before = compute_score(detected, ScoreConfig()).score
    after = compute_score(sig.apply_dismissals(detected, {sig.NO_WEBSITE: "wrong"}), ScoreConfig()).score
    assert before == 30 and after == 0
