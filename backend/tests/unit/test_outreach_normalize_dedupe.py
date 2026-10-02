"""Normalisation, deduplication and fixture parsing — pure, deterministic, offline."""

import pytest

from services.outreach_os.dedupe import build_candidate, dedupe
from services.outreach_os.normalize import (
    identity_hash,
    is_third_party_profile,
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
)
from services.outreach_os.sources import FixtureDirectoryAdapter, FixtureSiteFetcher
from services.outreach_os.types import RawListing


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Restaurant Chez Marcel SARL", "chez marcel"),
        ("CHEZ  MARCEL", "chez marcel"),
        ("Café des Quais", "cafe quais"),
        ("Pizzeria Il Forno", "pizzeria il forno"),
        ("L'Été & Co", "ete et co"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("04 78 12 34 56", "+33478123456"),
        ("+33 4 78 12 34 56", "+33478123456"),
        ("0033 4 78 12 34 56", "+33478123456"),
        ("04.78.12.34.56", "+33478123456"),
        ("+44 20 7946 0958", "+442079460958"),
        ("12345", None),
        ("", None),
        (None, None),
        ("not a phone", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.chez-marcel.example/accueil", "chez-marcel.example"),
        ("HTTP://Chez-Marcel.example:8080/x?y=1", "chez-marcel.example"),
        ("chez-marcel.example", "chez-marcel.example"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_third_party_profiles_are_not_own_websites():
    assert is_third_party_profile("facebook.com")
    assert is_third_party_profile("fr-fr.facebook.com")
    assert not is_third_party_profile("chez-marcel.example")
    assert not is_third_party_profile("notfacebook.com")
    assert not is_third_party_profile(None)


def test_normalize_email_and_identity_hash():
    assert normalize_email("  Contact@Chez-Marcel.Example ") == "contact@chez-marcel.example"
    assert normalize_email("not-an-email") is None
    assert identity_hash("email", "a@b.example") == identity_hash("email", "a@b.example")
    assert identity_hash("email", "a@b.example") != identity_hash("phone", "a@b.example")
    assert "a@b.example" not in identity_hash("email", "a@b.example")


def _listing(**kw):
    base = dict(external_id="x", name="N", source_name="s", source_url="u")
    return RawListing(**{**base, **kw})


def test_dedupe_merges_on_shared_domain_or_phone():
    a = build_candidate(
        _listing(external_id="1", name="Chez Marcel", website="https://www.m.example/", phone="04 78 12 34 56")
    )
    b = build_candidate(
        _listing(external_id="2", name="Marcel SARL", website="https://m.example/x", phone="0400000000")
    )
    c = build_candidate(_listing(external_id="3", name="Other", phone="+33 4 78 12 34 56"))
    merged = dedupe([a, b, c])
    assert len(merged) == 1  # a~b by domain, a~c by phone
    assert {listing.external_id for listing in merged[0].all_listings} == {"1", "2", "3"}


def test_dedupe_keeps_distinct_businesses_and_is_deterministic():
    items = [
        build_candidate(_listing(external_id=str(i), name=f"Biz {i}", city="Lyon", phone=f"04 78 00 00 0{i}"))
        for i in range(5)
    ]
    assert [c.listing.external_id for c in dedupe(items)] == ["0", "1", "2", "3", "4"]
    assert [c.listing.external_id for c in dedupe(list(items))] == ["0", "1", "2", "3", "4"]


def test_dedupe_does_not_merge_on_third_party_profile_or_empty_keys():
    a = build_candidate(_listing(external_id="1", name="A", website="https://facebook.com/a"))
    b = build_candidate(_listing(external_id="2", name="B", website="https://facebook.com/b"))
    c = build_candidate(_listing(external_id="3", name="C"))
    assert len(dedupe([a, b, c])) == 3


def test_dedupe_prefers_freshest_listing_and_fills_blanks():
    from datetime import date

    old = build_candidate(
        _listing(
            external_id="old",
            name="Chez Marcel",
            city="Lyon",
            phone="0478123456",
            hours="Mar-Sam",
            last_updated=date(2024, 1, 1),
        )
    )
    new = build_candidate(
        _listing(external_id="new", name="chez marcel", city="Lyon", phone="0478123456", last_updated=date(2026, 1, 1))
    )
    [entity] = dedupe([old, new])
    assert entity.listing.external_id == "new"
    assert entity.listing.hours == "Mar-Sam"  # blank filled from the older listing
    assert [m.external_id for m in entity.merged_from] == ["old"]


def test_fixture_directory_produces_nine_listings_and_seven_entities():
    listings = FixtureDirectoryAdapter().fetch()
    assert len(listings) == 9
    assert all(listing.source_name == "fixture_directory" for listing in listings)
    entities = dedupe([build_candidate(listing) for listing in listings])
    assert len(entities) == 7  # d-007 merges into d-001, d-008 into d-005
    by_id = {e.listing.external_id: e for e in entities}
    assert {m.external_id for m in by_id["d-001"].merged_from} == {"d-007"}
    assert {m.external_id for m in by_id["d-005"].merged_from} == {"d-008"}


def test_fixture_directory_parses_fields():
    first = FixtureDirectoryAdapter().fetch()[0]
    assert (first.name, first.city, first.postcode) == ("Chez Marcel", "Lyon", "69003")
    assert first.website == "https://www.chez-marcel.example/"
    assert first.last_updated.isoformat() == "2026-05-12"


def test_fixture_site_fetcher_distinguishes_unchecked_from_failed():
    fetcher = FixtureSiteFetcher()
    assert fetcher.fetch("https://never-heard-of.example") is None
    failed = fetcher.fetch("https://sushi-kaze.example")
    assert failed is not None and failed.status == 503 and failed.html is None
    ok = fetcher.fetch("https://il-forno.example")
    assert ok is not None and ok.status == 200 and "Il Forno" in (ok.html or "")
