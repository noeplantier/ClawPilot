from services.outreach_os import heat as h

FULL = {f: "x" for f in h.INFO_FIELDS}


def test_information_counts_only_what_is_really_known():
    assert h.known_fields(
        {"email": "a@b.example", "phone": " ", "website": None, "city": "Lyon", "vertical": "unspecified"}
    ) == ("email", "city")
    for blank in ("", "  ", "unknown", "Unknown", "UNSPECIFIED", "n/a", None, 0, 12):
        assert not h.is_known(blank)  # an unknown or a default is never a value; only text can be known
    assert h.is_known("Lyon")


def test_information_share_uses_integer_arithmetic_with_halves_up():
    assert [h.info_pct(k) for k in range(9)] == [0, 13, 25, 38, 50, 63, 75, 88, 100]


def test_heat_blends_score_and_information_and_never_treats_not_scored_as_zero():
    assert h.heat_of(FULL, 80).value == 90 and h.heat_of(FULL, 80).scored is True
    unscored = h.heat_of(FULL, None)
    assert unscored.value == 100 and unscored.scored is False and unscored.score is None  # ranked on information alone
    assert h.heat_of({}, 0).value == 0 and h.heat_of({}, 0).scored is True  # a real score of 0 is a score
    assert h.heat_of({"email": "a@b.example"}, 50).value == (50 + 13 + 1) // 2


def test_tiers_and_what_is_missing_are_reported():
    assert [h.tier_of(v) for v in (0, 39, 40, 64, 65, 100)] == ["cold", "cold", "warm", "warm", "hot", "hot"]
    heat = h.heat_of({"email": "a@b.example", "phone": "+33 4 00 00 00 00"}, 70)
    assert heat.known == ("email", "phone") and "website" in heat.missing and len(heat.known) + len(heat.missing) == 8
    assert heat.tier == "warm" and heat.info_pct == 25


def test_top_is_the_hot_lead_at_80_or_more_and_is_never_a_guess():
    assert [h.is_top(v) for v in (0, 64, 65, 79, 80, 100)] == [False, False, False, False, True, True]
    assert h.heat_of(FULL, 60).top is True  # (60 + 100 + 1) // 2 = 80
    assert h.heat_of(FULL, 58).top is False  # 79
    assert h.heat_of(FULL, None).top is True  # not scored, fully known: ranked on information alone, and says so
    assert h.heat_of({}, 100).top is False  # (100 + 0 + 1) // 2 = 50: a score without any information is not TOP


def test_a_lead_is_empty_when_nothing_can_reach_it_not_when_it_merely_lacks_a_city():
    only_name_fields = {
        "city": "Lyon",
        "company": "Chez Marcel",
        "vertical": "restaurants",
        "country": "FR",
        "title": "Owner",
    }
    assert h.has_contact(only_name_fields) is False and h.heat_of(only_name_fields, None).has_contact is False
    for field in h.CONTACT_FIELDS:
        assert h.has_contact({field: "x"}) is True
    for blank in ("", "  ", "unknown", "unspecified", "n/a", None):
        assert h.has_contact({"email": blank, "phone": blank, "website": blank}) is False  # an unknown is not a way in
    assert h.heat_of({}, None).has_contact is False


def test_the_map_shows_only_hot_leads_that_can_be_called_and_e_mailed():
    ready = {f: "x" for f in h.INFO_FIELDS}
    assert h.is_map_ready(ready, 60) is True  # hot, phone and e-mail known
    assert h.is_map_ready({**ready, "website": None}, 60) is True  # a website is a bonus, never required
    assert h.is_map_ready({**ready, "phone": "unknown"}, 60) is False  # no phone
    assert h.is_map_ready({**ready, "email": ""}, 60) is False  # no e-mail
    assert h.is_map_ready(ready, 0) is False  # (0 + 100 + 1) // 2 = 50: warm, however reachable
    assert (
        h.is_map_ready({"phone": "+33 4 00 00 00 00", "email": "a@b.example"}, 100) is False
    )  # (100 + 25 + 1) // 2 = 63
