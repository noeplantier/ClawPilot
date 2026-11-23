"""Three offers, one per case: saved, read back with who receives each; the older single-offer screen still works."""

import requests

from tests.test_map_quick_add import API, _org

ITEM = {"pitch": "Un site clair qui présente votre activité et vos horaires.", "cta": "Un appel de 15 minutes ?"}
THREE = {
    "language": "fr",
    "default": "seo_geo",
    "offers": {
        "creation": {"name": "Création de site", **ITEM},
        "refonte_maintenance": {"name": "Refonte et maintenance", **ITEM},
        "seo_geo": {"name": "SEO / GEO", **ITEM},
    },
}


def test_nothing_is_configured_and_nothing_is_invented_at_first():
    _, h, _ = _org()
    out = requests.get(f"{API}/settings/offers", headers=h).json()
    assert out["configured"] is False and [c["kind"] for c in out["cases"]] == [
        "refonte_maintenance",
        "creation",
        "seo_geo",
    ]
    assert all(c["configured"] is False and c["offer"] is None for c in out["cases"])


def test_three_offers_are_saved_with_who_receives_each():
    _, h, _ = _org()
    r = requests.put(f"{API}/settings/offers", headers=h, json=THREE)
    assert r.status_code == 200
    cases = {c["kind"]: c for c in r.json()["cases"]}
    assert all(c["configured"] for c in cases.values())
    assert "sans site identifié" in cases["creation"]["when"]
    assert "par défaut" in cases["seo_geo"]["when"]  # the default also serves the prospects whose site is unknown
    assert requests.get(f"{API}/settings/offer", headers=h).json()["offer"]["name"] == "SEO / GEO"


def test_the_default_must_be_one_of_the_offers():
    _, h, _ = _org()
    bad = {**THREE, "default": "creation", "offers": {"seo_geo": THREE["offers"]["seo_geo"]}}
    r = requests.put(f"{API}/settings/offers", headers=h, json=bad)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "offers_incomplete"


def test_the_older_screen_edits_the_default_offer_only_and_keeps_the_others():
    _, h, _ = _org()
    requests.put(f"{API}/settings/offers", headers=h, json=THREE).raise_for_status()
    single = {"name": "SEO local", **ITEM, "language": "fr"}
    requests.put(f"{API}/settings/offer", headers=h, json=single).raise_for_status()
    cases = {c["kind"]: c for c in requests.get(f"{API}/settings/offers", headers=h).json()["cases"]}
    assert cases["seo_geo"]["offer"]["name"] == "SEO local"
    assert cases["creation"]["offer"]["name"] == "Création de site"  # never erased


def test_an_older_single_offer_is_shown_for_every_case():
    _, h, _ = _org()
    requests.put(
        f"{API}/settings/offer", headers=h, json={"name": "Site vitrine", **ITEM, "language": "fr"}
    ).raise_for_status()
    out = requests.get(f"{API}/settings/offers", headers=h).json()
    assert out["default"] == "single" and all(c["offer"]["name"] == "Site vitrine" for c in out["cases"])
