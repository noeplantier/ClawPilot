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
