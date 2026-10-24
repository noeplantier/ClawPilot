"""Pure guards for public map source normalization; no network or database calls."""

from tasks.prospecting_tasks import CATEGORIES, QUERY_VERSION, _key, _overpass_query


def test_bbox_cache_key_normalizes_precision_and_includes_category_version():
    assert _key([48.123456, 2.123456, 48.2, 2.2], "cafe") == _key([48.12346, 2.12346, 48.20001, 2.20001], "cafe")
    assert _key([48.123456, 2.123456, 48.2, 2.2], "cafe") != _key([48.123456, 2.123456, 48.2, 2.2], "restaurant")
    assert QUERY_VERSION == "v1"


def test_overpass_query_is_bounded_and_uses_category_selector():
    query = _overpass_query([48.0, 2.0, 48.1, 2.1], "cafe")
    assert "node[amenity=\"cafe\"](48.0,2.0,48.1,2.1)" in query
    assert "way[amenity=\"cafe\"]" in query
    assert "relation[amenity=\"cafe\"]" in query
    assert set(CATEGORIES) == {"restaurant", "cafe", "hotel", "shop", "office", "beauty", "dentist", "company"}
