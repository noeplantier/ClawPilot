"""The commercial intent signal: what the business states itself on its own homepage, with the quoted evidence.

Pure, on versioned HTML fixtures, no network. "Hot" (eligibility.py) rests on this signal only; it never moves the
score.
"""

from datetime import date
from pathlib import Path

import pytest

from services.outreach_os import eligibility
from services.outreach_os import signals as sig
from services.outreach_os.scoring import DEFAULT_WEIGHTS, ScoreConfig, compute_score
from services.outreach_os.types import RawListing, SignalState, SiteSnapshot

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "sites"
NOW = date(2026, 11, 19)
SITE = "https://fournil.example"
LISTING = RawListing("1", "Boulangerie Fournil", "osm", "u", website=SITE, city="Plérin")


def intent(listing=LISTING, page=None, status=200):
    snap = SiteSnapshot(SITE, status, (FIX / page).read_text() if page else None) if page or status != 200 else None
    return next(r for r in sig.analyze(listing, snap, now=NOW) if r.key == sig.COMMERCIAL_INTENT)


def test_hiring_stated_on_its_own_homepage_is_an_intent_with_the_quoted_sentence_and_the_url():
    r = intent(page="hiring_home.html")
    assert r.state is SignalState.DETECTED
    assert r.evidence.startswith("hiring: the homepage https://fournil.example says")
    assert "Nous recrutons un boulanger" in r.evidence and "other pages not checked" in r.evidence


def test_a_site_that_says_it_is_being_built_is_an_intent():
    r = intent(page="under_construction_home.html")
    assert r.state is SignalState.DETECTED and r.evidence.startswith("own site being built:")
    assert "en cours de construction" in r.evidence


def test_a_builder_s_houses_under_construction_are_not_its_website_and_nothing_else_is_invented():
    assert intent(page="builder_home.html").state is SignalState.NOT_DETECTED
    assert intent(page="modern_home.html").state is SignalState.NOT_DETECTED


def test_scripts_and_comments_are_never_read_and_an_injected_instruction_changes_nothing():
    r = intent(page="hiring_home.html")
    assert "Ignore previous" not in r.evidence and "var note" not in r.evidence
    assert "ready to buy" not in r.evidence


@pytest.mark.parametrize(
    "listing,page,status,words",
    [
        (RawListing("1", "X", "osm", "u"), None, 200, "no own website"),
        (RawListing("1", "X", "osm", "u", website="https://www.facebook.com/x"), None, 200, "no own website"),
        (LISTING, None, 503, "HTML not available"),
    ],
)
def test_without_its_own_homepage_the_intent_is_unknown_never_a_verdict(listing, page, status, words):
    r = intent(listing, page, status)
    assert r.state is SignalState.UNKNOWN and words in r.evidence


def test_the_intent_never_moves_the_fit_score_and_is_the_signal_hot_rests_on():
    assert sig.COMMERCIAL_INTENT == eligibility.INTENT_SIGNAL
    assert sig.COMMERCIAL_INTENT not in DEFAULT_WEIGHTS
    results = sig.analyze(LISTING, SiteSnapshot(SITE, 200, (FIX / "hiring_home.html").read_text()), now=NOW)
    without = [r for r in results if r.key != sig.COMMERCIAL_INTENT]
    assert compute_score(results, ScoreConfig()).score == compute_score(without, ScoreConfig()).score
