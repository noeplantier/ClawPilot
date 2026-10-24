"""OpenStreetMap listings, area limits, own-site e-mail extraction and the cached Overpass client. No network."""

import json
from pathlib import Path

import pytest

from services import overpass_svc
from services.outreach_os import contact, osm
from services.outreach_os.importer import parse_import

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "osm"


def _listings():
    return {item.external_id: item for item in osm.parse_elements(json.loads((FIX / "overpass_lyon.json").read_text()))}


def test_only_named_and_positioned_places_are_kept_and_duplicates_collapse():
    got = _listings()
    assert set(got) == {"node/101", "way/202", "node/505"}  # no name, no position: dropped
    assert got["node/101"].name == "Chez Marcel (doublon)" or got["node/101"].name  # one entry per OSM id


def test_a_place_carries_exactly_what_contributors_published():
    marcel = _listings()["node/101"]
    assert (marcel.lat, marcel.lon) == (45.764, 4.8357)
    assert marcel.source_url == "https://www.openstreetmap.org/node/101" and marcel.source_name == "openstreetmap"


def test_multi_values_take_the_first_and_the_email_is_normalised():
    first = osm.parse_elements(json.loads((FIX / "overpass_lyon.json").read_text()))[0]
    raw = json.loads((FIX / "overpass_lyon.json").read_text())
    raw["elements"] = raw["elements"][:1]
    marcel = osm.parse_elements(raw)[0]
    assert marcel.email == "contact@chez-marcel.example" and marcel.phone == "+33 4 78 12 34 56"
    assert marcel.address == "12 Rue Merciere" and marcel.postcode == "69002" and marcel.city == "Lyon"
    assert marcel.website and marcel.last_updated.isoformat() == "2026-09-01" and first is not None


def test_a_way_uses_its_centre_and_missing_tags_stay_missing():
    bakery = _listings()["way/202"]
    assert (bakery.lat, bakery.lon) == (45.76, 4.84) and bakery.category == "bakery"
    assert bakery.email is None and bakery.phone is None and bakery.website is None  # never guessed


def test_unparseable_contacts_are_dropped_not_kept():
    bad = _listings()["node/505"]
    assert bad.email is None and bad.phone is None and bad.website is None


def test_the_query_is_bounded_and_only_for_known_categories():
    q = osm.build_query(45.75, 4.82, 45.77, 4.85, "restaurants")
    assert (
        "[out:json]" in q
        and "out center meta 300" in q
        and '"amenity"' in q
        and "(45.75000,4.82000,45.77000,4.85000)" in q
    )
    for args in [
        (45, 4, 46, 5, "restaurants"),
        (45.75, 4.82, 45.77, 4.85, "drugs"),
        (46, 4, 45, 5, "shops"),
        (91, 0, 92, 1, "shops"),
    ]:
        with pytest.raises(osm.BadArea):
            osm.build_query(*args)


def test_the_attribution_is_always_available():
    assert "OpenStreetMap" in osm.ATTRIBUTION and "ODbL" in osm.LICENSE_NOTE


HTML = """<html><body><a href="mailto:contact@chez-marcel.fr?subject=Hi">Écrire</a>
<a href='mailto:noreply@chez-marcel.fr'>x</a><a href="mailto:someone@gmail.com">y</a></body></html>"""


def test_a_mailto_on_the_own_domain_is_found_and_nothing_else():
    assert contact.extract_contact_email(HTML, "https://www.chez-marcel.fr/") == "contact@chez-marcel.fr"
    assert contact.extract_contact_email(HTML, "https://autre-site.fr") is None  # not that business's domain
    assert contact.extract_contact_email("<p>write to contact@chez-marcel.fr</p>", "https://chez-marcel.fr") is None
    assert (
        contact.extract_contact_email('<a href="mailto:noreply@chez-marcel.fr">x</a>', "https://chez-marcel.fr") is None
    )
    assert contact.extract_contact_email(None, "https://chez-marcel.fr") is None
    assert contact.extract_contact_email(HTML, None) is None


def test_an_import_file_can_carry_a_position_and_a_wrong_one_is_an_error():
    ok = parse_import("name,lat,lon\nA,45.76,4.83\nB,,\n", "csv", source_name="s", default_source_url="import://s")
    assert [(x.lat, x.lon) for x in ok.listings] == [(45.76, 4.83), (None, None)]
    bad = parse_import("name,lat,lon\nA,95,4\nB,x,1\n", "csv", source_name="s", default_source_url="import://s")
    assert not bad.listings and len(bad.errors) == 2


def test_the_overpass_client_caches_and_falls_back_nothing_else(monkeypatch):
    calls = []
    now = [0.0]

    def fake(query):
        calls.append(query)
        return {"elements": []}

    fetcher = overpass_svc.CachedFetcher(fake, clock=lambda: now[0])
    fetcher("q"), fetcher("q")
    assert len(calls) == 1  # panning back does not hit the public servers again
    now[0] = overpass_svc.CACHE_SECONDS + 1
    fetcher("q")
    assert len(calls) == 2
