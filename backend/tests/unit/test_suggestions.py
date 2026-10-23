from services.outreach_os import signals as sig
from services.outreach_os import suggestions as sg


def C(
    i,
    name,
    *,
    prospect=True,
    status="pending",
    vertical="bakery",
    city="Lyon",
    stage=None,
    heat=50,
    tier=None,
    email=False,
    phone=False,
    signals=(),
    sendable=False,
):
    tier = tier or ("hot" if heat >= 65 else "warm" if heat >= 40 else "cold")
    return sg.Candidate(
        i,
        name,
        prospect,
        status if prospect else None,
        vertical,
        city,
        stage,
        heat,
        tier,
        email,
        phone,
        frozenset(signals),
        sendable,
    )


def test_nothing_is_suggested_without_enough_real_data():
    assert sg.suggest([], dry_run=True) == []
    assert sg.suggest([C("1", "Solo")], dry_run=True) == []  # one person is not a group
    assert (
        sg.suggest([C("1", "A", vertical=None), C("2", "B", vertical=None)], dry_run=True) == []
    )  # an unknown is never grouped as a value


def test_a_segment_groups_a_known_vertical_and_a_known_city_case_insensitively():
    items = [
        C("1", "Chez A", city="Lyon", vertical="Bakery"),
        C("2", "Chez B", city="lyon", vertical="bakery"),
        C("3", "Chez C", city="Paris"),
    ]
    (s,) = sg.suggest(items, dry_run=True)
    assert s.kind == "segment" and s.title == "Bakery in Lyon" and s.total == 2 and sorted(s.member_ids) == ["1", "2"]


def test_signal_groups_use_only_detected_signals_and_name_the_angle():
    items = [C(str(i), f"P{i}", city=f"City{i}", signals=[sig.NO_WEBSITE]) for i in range(3)] + [
        C("9", "Other", signals=[sig.OUTDATED_TECHNOLOGY])
    ]
    out = sg.suggest(items, dry_run=True)
    assert [s.kind for s in out] == ["signal"]
    assert out[0].title == "No own website listed" and out[0].angle == "Offer: a first website" and out[0].total == 3
    assert "detected on their own pages" in out[0].rationale


def test_rejected_prospects_are_never_suggested():
    items = [C("1", "A", status="rejected"), C("2", "B", status="rejected"), C("3", "C", status="rejected")]
    assert sg.suggest(items, dry_run=False) == []


def test_eligibility_follows_the_send_rules_and_the_page_says_what_blocks():
    members = [
        C("1", "A", email=True),
        C("2", "B", phone=True, status="approved"),
        C("3", "C", email=True, status="approved", sendable=True),
    ]
    dry = sg.suggest(members, dry_run=True)[0]
    assert dry.eligible == 1 and dry.eligible_ids == ["3"] and dry.blocked_reason is None  # one can join today
    none_ready = sg.suggest(members[:2], dry_run=True)[0]
    assert none_ready.eligible == 0 and "dry-run" in none_ready.blocked_reason
    live = sg.suggest([C("1", "A", email=True), C("2", "B", email=True)], dry_run=False)[0]
    assert (
        live.eligible == 0
        and live.pending_review == 2
        and "wait for approval in the review queue" in live.blocked_reason
    )
    crm = sg.suggest(
        [
            C("1", "A", prospect=False, stage="new", email=True, sendable=True),
            C("2", "B", prospect=False, stage="new", phone=True, sendable=True),
        ],
        dry_run=True,
    )
    assert [s.kind for s in crm] == ["new_leads"] and crm[0].eligible == 2 and crm[0].blocked_reason is None


def test_ranking_puts_the_hottest_groups_first_and_ids_are_stable():
    hot = [
        C("1", "H1", vertical="hotel", city="Nice", heat=90, email=True),
        C("2", "H2", vertical="hotel", city="Nice", heat=80, email=True),
    ]
    cold = [C("3", "C1", heat=10), C("4", "C2", heat=20)]
    out = sg.suggest(cold + hot, dry_run=True)
    assert out[0].title.startswith("Hotel in Nice") or out[0].kind == "hot"
    assert out[0].priority >= out[-1].priority
    assert [s.id for s in sg.suggest(hot + cold, dry_run=True)] == [
        s.id for s in out
    ]  # the order of the input does not matter
    assert all(len(s.id) == 12 for s in out)


def test_at_most_eight_suggestions_and_examples_are_the_hottest_names():
    many = []
    for n in range(12):
        many += [
            C(f"{n}a", f"Alpha{n}", vertical=f"v{n}", city="X", heat=10 + n),
            C(f"{n}b", f"Beta{n}", vertical=f"v{n}", city="X", heat=20 + n),
        ]
    out = sg.suggest(many, dry_run=True)
    assert len(out) == sg.MAX_SUGGESTIONS
    assert out[0].examples[0].startswith("Beta")  # hottest first inside a group
