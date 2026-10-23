from services.outreach_os import map_jobs
from services.outreach_os.types import RawListing


def L(ext, name="Chez Marcel", lat=45.7641, lon=4.8358, **kw):
    return RawListing(
        external_id=ext, name=name, source_name="openstreetmap", source_url=f"https://x/{ext}", lat=lat, lon=lon, **kw
    )


def test_nearby_searches_share_one_cache_entry_and_the_snapped_area_contains_the_asked_one():
    a = map_jobs.Bbox(45.7501, 4.8201, 45.7699, 4.8499)
    b = map_jobs.Bbox(45.7512, 4.8223, 45.7688, 4.8478)
    assert map_jobs.cache_key(a, "bakeries") == map_jobs.cache_key(b, "bakeries")
    assert map_jobs.cache_key(a, "bakeries") != map_jobs.cache_key(a, "hotels")
    snapped = map_jobs.snap_bbox(a)
    assert snapped.south <= a.south and snapped.west <= a.west and snapped.north >= a.north and snapped.east >= a.east


def test_the_cache_key_changes_with_the_query_version(monkeypatch):
    box = map_jobs.Bbox(45.75, 4.82, 45.77, 4.85)
    before = map_jobs.cache_key(box, "bakeries")
    monkeypatch.setattr(map_jobs, "QUERY_VERSION", "osm-v2")
    assert map_jobs.cache_key(box, "bakeries") != before


def test_the_same_source_id_is_one_place():
    kept = map_jobs.dedupe([L("node/1"), L("node/1", name="Other")])
    assert [p.external_id for p in kept] == ["node/1"]


def test_the_same_name_at_the_same_spot_is_one_place_and_the_richer_entry_wins():
    poor = L("node/1")
    rich = L(
        "way/9", name="CHEZ  marcel", lat=45.76412, lon=4.83581, phone="+33 4 78 00 00 00", website="https://m.example"
    )
    kept = map_jobs.dedupe([poor, rich])
    assert [p.external_id for p in kept] == ["way/9"]
    assert [p.external_id for p in map_jobs.dedupe([rich, poor])] == ["way/9"]  # order does not decide


def test_accents_and_punctuation_do_not_hide_a_duplicate_but_distant_namesakes_stay_apart():
    kept = map_jobs.dedupe(
        [
            L("node/1", name="Café de l'Été"),
            L("node/2", name="cafe de l ete"),
            L("node/3", name="Café de l'Été", lat=45.80),
        ]
    )
    assert sorted(p.external_id for p in kept) == ["node/1", "node/3"]


def test_error_classes():
    c = map_jobs.classify_failures
    assert c([]) == "overpass_unreachable"
    assert c(["timeout", "timeout"]) == "overpass_timeout"
    assert c(["timeout", "busy"]) == "overpass_busy"
    assert c(["unreachable", "timeout"]) == "overpass_unreachable"
    assert c(["bad_answer", "bad_answer"]) == "overpass_bad_answer"
    assert c(["timeout", "too_large"]) == "overpass_too_large"
    assert set(map_jobs.HINTS) == set(map_jobs.ERROR_CODES)
