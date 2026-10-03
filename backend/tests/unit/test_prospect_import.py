"""Parsing and validating a supplied prospect list: pure, offline."""

import json
from datetime import date

import pytest

from services.outreach_os import signals as sig
from services.outreach_os.importer import (
    MAX_ROWS,
    ImportRejected,
    ListAdapter,
    NoNetworkFetcher,
    parse_import,
)
from services.outreach_os.types import RawListing, SignalState

KW = dict(source_name="import:abcd1234", default_source_url="import://import:abcd1234")

CSV = (
    "Nom,E-mail,Téléphone,Site web,Ville,Colonne inconnue\n"
    '"Atelier Dupont",contact@atelier-dupont.example,01 23 45 67 89,https://atelier-dupont.example,Lyon,x\n'
    "Boulangerie Martin,martin@boulangerie-martin.example,,,Tours,y\n"
)


def test_csv_with_french_headers_and_unknown_columns():
    out = parse_import(CSV, "csv", **KW)
    assert out.rows_total == 2 and not out.errors
    assert out.ignored_columns == ["Colonne inconnue"]
    first, second = out.listings
    assert (first.name, first.email, first.city, first.website) == (
        "Atelier Dupont", "contact@atelier-dupont.example", "Lyon", "https://atelier-dupont.example",
    )  # fmt: skip
    assert second.website is None and second.phone is None  # an empty cell is None, never an invented value
    assert first.source_name == "import:abcd1234" and first.source_url == "import://import:abcd1234"


def test_semicolon_delimiter_bom_and_json_shapes():
    semi = "﻿name;email\nAcme;a@acme.example\n"
    assert parse_import(semi, "csv", **KW).listings[0].email == "a@acme.example"
    as_list = json.dumps([{"name": "A", "email": "a@a.example"}, {"company": "B", "extra": 1}])
    out = parse_import(as_list, "json", **KW)
    assert [x.name for x in out.listings] == ["A", "B"] and out.ignored_columns == ["extra"]
    wrapped = json.dumps({"items": [{"name": "C"}]})
    assert parse_import(wrapped, "json", **KW).listings[0].name == "C"


@pytest.mark.parametrize(
    "row, message",
    [
        ("name,email\n,a@a.example", "missing name"),
        ("name,email\nA,not-an-email", "invalid e-mail"),
        ("name,phone\nA,12", "unreadable phone"),
        ("name,website\nA,javascript:alert(1)", "http"),
        ("name,website\nA,data:text/html;base64,AAAA", "http"),
        ("name,last_updated\nA,yesterday", "YYYY-MM-DD"),
    ],
)
def test_bad_rows_are_reported_with_their_number_and_skipped(row, message):
    out = parse_import(row, "csv", **KW)
    assert not out.listings and len(out.errors) == 1
    assert out.errors[0].row == 1 and message in out.errors[0].message


def test_good_rows_survive_next_to_bad_ones():
    out = parse_import("name,email\nA,a@a.example\nB,nope\nC,c@c.example\n", "csv", **KW)
    assert [x.name for x in out.listings] == ["A", "C"] and [e.row for e in out.errors] == [2]


@pytest.mark.parametrize(
    "content, fmt, message",
    [
        ("", "csv", "no header"),
        ("email,city\na@a.example,Lyon", "csv", "no name column"),
        ("{not json", "json", "invalid JSON"),
        ('{"a": 1}', "json", "array of objects"),
        ("name\nA", "xml", "unknown format"),
    ],
)
def test_an_unusable_file_is_rejected_as_a_whole(content, fmt, message):
    with pytest.raises(ImportRejected, match=message):
        parse_import(content, fmt, **KW)


def test_size_and_row_limits():
    with pytest.raises(ImportRejected, match="too many rows"):
        parse_import("name\n" + "\n".join(f"n{i}" for i in range(MAX_ROWS + 1)), "csv", **KW)
    with pytest.raises(ImportRejected, match="too large"):
        parse_import("name\n" + "x" * 2_100_000, "csv", **KW)


def test_control_characters_are_stripped_and_long_cells_truncated():
    out = parse_import('name,description\n"A\x00B\x1f","' + "z" * 5000 + '"\n', "csv", **KW)
    assert out.listings[0].name == "A B" and len(out.listings[0].description) == 2000


def test_ids_are_stable_so_reimporting_the_same_file_creates_no_new_source_rows():
    a = parse_import(CSV, "csv", **KW).listings
    b = parse_import(CSV, "csv", **KW).listings
    assert [x.external_id for x in a] == [x.external_id for x in b] and a[0].external_id != a[1].external_id
    assert parse_import(CSV, "csv", **KW).content_sha256 == parse_import(CSV, "csv", **KW).content_sha256


def test_the_adapter_and_the_fetcher_never_touch_the_network():
    listing = parse_import(CSV, "csv", **KW).listings[0]
    assert ListAdapter("import:x", "note", [listing]).fetch() == [listing]
    assert NoNetworkFetcher().fetch("https://example.test") is None


# ---- signals on a supplied list: absence is UNKNOWN, never a finding -------------------------------------------
BARE = RawListing(external_id="1", name="X", source_name="import:x", source_url="u")


def _by_key(listing, trust_absence):
    return {r.key: r for r in sig.analyze(listing, None, now=date(2026, 6, 1), trust_absence=trust_absence)}


def test_an_empty_cell_in_a_supplied_list_is_not_evidence_of_no_website():
    trusted = _by_key(BARE, True)[sig.NO_WEBSITE]
    supplied = _by_key(BARE, False)[sig.NO_WEBSITE]
    assert trusted.state is SignalState.DETECTED  # a complete directory: absence is a finding
    assert supplied.state is SignalState.UNKNOWN and "not evidence" in supplied.evidence


def test_incomplete_listing_is_unknown_for_a_supplied_list_but_a_third_party_only_site_is_still_observed():
    assert _by_key(BARE, False)[sig.INCOMPLETE_LISTING].state is SignalState.UNKNOWN
    facebook = RawListing(
        external_id="2", name="Y", source_name="import:x", source_url="u", website="https://facebook.com/y"
    )
    assert _by_key(facebook, False)[sig.NO_WEBSITE].state is SignalState.DETECTED  # observed, not inferred


def test_nothing_is_fetched_so_site_signals_are_unknown():
    with_site = RawListing(
        external_id="3", name="Z", source_name="import:x", source_url="u", website="https://z.example"
    )
    states = {k: r.state for k, r in _by_key(with_site, False).items()}
    assert states[sig.WEBSITE_UNREACHABLE] is SignalState.UNKNOWN
    assert (
        states[sig.NOT_MOBILE_FRIENDLY] is SignalState.UNKNOWN
        and states[sig.BOOKING_PAGE_MISSING] is SignalState.UNKNOWN
    )
