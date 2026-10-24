"""Per-city counts of the map's town search: spellings that mean one town are merged, nothing is invented."""

import pytest

from services.outreach_os import cities


@pytest.mark.parametrize(
    "written",
    ["Saint-Étienne", "saint etienne", "SAINT ETIENNE", "St-Etienne", " st  étienne ", "Saint’Étienne"],
)
def test_one_town_has_one_key_whatever_the_spelling(written):
    assert cities.fold(written) == "saint etienne"


def test_ste_is_sainte_but_a_word_that_merely_starts_with_st_is_kept():
    assert cities.fold("Ste-Foy-lès-Lyon") == "sainte foy les lyon"
    assert cities.fold("Strasbourg") == "strasbourg"
    assert cities.fold("L'Isle-d'Abeau") == "l isle d abeau"


@pytest.mark.parametrize("blank", ["", "   ", "-", "’"])
def test_a_blank_city_has_no_key(blank):
    assert cities.fold(blank) == ""


def test_merge_adds_up_the_spellings_and_keeps_the_most_used_one():
    rows = [
        ("Lyon", "hot", 2),
        ("lyon", "hot", 1),
        ("LYON", "cold", 4),
        ("Saint-Étienne", "warm", 3),
        ("St Etienne", "hot", 1),
    ]
    out = {c["key"]: c for c in cities.merge(rows)}
    assert out["lyon"] == {"city": "Lyon", "key": "lyon", "hot": 3, "warm": 0, "cold": 4, "total": 7}
    assert out["saint etienne"] == {
        "city": "Saint-Étienne",
        "key": "saint etienne",
        "hot": 1,
        "warm": 3,
        "cold": 0,
        "total": 4,
    }


def test_merge_lists_the_hottest_towns_first_then_the_biggest_then_by_name():
    rows = [
        ("Brest", "cold", 9),
        ("Annecy", "hot", 1),
        ("Caen", "hot", 1),
        ("Dijon", "hot", 3),
        ("Évreux", "warm", 5),
    ]
    assert [c["city"] for c in cities.merge(rows)] == ["Dijon", "Annecy", "Caen", "Brest", "Évreux"]


def test_a_capitalised_spelling_is_shown_rather_than_a_shouted_or_lowercase_one():
    rows = [("LYON", "hot", 5), ("lyon", "hot", 3), ("Lyon", "hot", 1)]
    assert cities.merge(rows)[0]["city"] == "Lyon"
    assert cities.merge([("LYON", "hot", 5), ("lyon", "hot", 3)])[0]["city"] == "LYON"  # nothing better: the most used


def test_the_order_of_the_database_answer_does_not_matter():
    rows = [("Lyon", "hot", 1), ("lyon", "hot", 1), ("Lyon", "cold", 1), ("lyon", "cold", 1)]
    assert cities.merge(rows) == cities.merge(list(reversed(rows)))
    assert cities.merge(rows)[0]["city"] == "Lyon"  # a tie takes the alphabetical first, always


def test_merge_ignores_blank_towns_unknown_tiers_and_empty_counts():
    rows = [("", "hot", 5), ("  ", "hot", 1), ("Nice", "boiling", 2), ("Nice", "hot", 0), ("Nice", "warm", 1)]
    assert cities.merge(rows) == [{"city": "Nice", "key": "nice", "hot": 0, "warm": 1, "cold": 0, "total": 1}]


def test_no_lead_no_town():
    assert cities.merge([]) == []
