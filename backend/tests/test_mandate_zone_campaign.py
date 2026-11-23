"""A mandate rests on a zone campaign: an individual campaign (no zone) is never offered, and a wrong id says why."""

import requests

from tests.test_map_quick_add import API, _org

MANDATE = {
    "name": "Mandat test",
    "daily_cap": 5,
    "total_cap": 10,
    "days": 7,
    "window_start_hour": 8,
    "window_end_hour": 18,
    "min_delay_seconds": 60,
    "search_every_hours": 24,
    "ai_budget": 0,
    "stop_rules": {"max_bounce_rate": 0.05, "max_opt_out_rate": 0.1, "min_sample": 20},
}


def test_an_individual_campaign_is_not_listed_as_a_zone_campaign():
    _, h, _ = _org()
    launch = requests.post(f"{API}/launches", headers=h, json={"name": "Campagne individuelle", "size": 5})
    assert launch.status_code == 200
    assert requests.get(f"{API}/journeys", headers=h).json()["items"] == []


def test_a_mandate_on_a_campaign_without_a_zone_says_so():
    _, h, _ = _org()
    launch_id = requests.post(f"{API}/launches", headers=h, json={"name": "Individuelle", "size": 5}).json()["launch"][
        "id"
    ]
    r = requests.post(f"{API}/mandates", headers=h, json={**MANDATE, "campaign_id": launch_id})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_a_zone_campaign"


def test_a_mandate_on_an_unknown_or_foreign_campaign_is_not_found():
    _, h, _ = _org()
    _, other, _ = _org()
    foreign = requests.post(f"{API}/launches", headers=other, json={"name": "Autre compte", "size": 5}).json()[
        "launch"
    ]["id"]
    for campaign_id in ("00000000-0000-4000-8000-000000000000", "not-an-id", foreign):
        r = requests.post(f"{API}/mandates", headers=h, json={**MANDATE, "campaign_id": campaign_id})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "campaign_not_found", campaign_id
