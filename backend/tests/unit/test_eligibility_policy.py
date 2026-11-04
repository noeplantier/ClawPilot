"""The pure eligibility policy (no database): what makes a prospect qualified, hot, or still to enrich."""

from datetime import datetime, timedelta, timezone

from services.outreach_os import eligibility as policy

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def lead(**over):
    base = {
        "full_name": "Chez Alice",
        "email": "contact@chez-alice.fr",
        "phone": "+33 6 12 34 56 78",
        "fit_score": 72,
        "qualification_scored_at": NOW - timedelta(days=1),
        "review_status": "pending",
    }
    return {**base, **over}


def source(**over):
    base = {
        "id": "s1",
        "source_name": "osm",
        "source_url": "https://www.openstreetmap.org/node/1",
        "license_note": "ODbL",
        "fetched_at": NOW - timedelta(days=1),
        "fields": {"address": "12 rue du Port", "lat": 48.5, "lon": -2.7},
    }
    return {**base, **over}


def decide(lead_=None, sources=None, **kw):
    return policy.evaluate(lead_ or lead(), sources=[source()] if sources is None else sources, now=NOW, **kw)


def test_email_phone_address_and_position_are_enough_without_a_website_or_whatsapp():
    out = decide()
    assert out["eligible"] and out["status"] == "qualified" and out["missing_fields"] == []
    assert out["priority"] == "qualified" and out["priority_label"] == "Qualifié prioritaire" and not out["is_hot"]
    assert out["policy_version"] == policy.POLICY_VERSION


def test_a_website_changes_nothing_either_way():
    assert decide(lead(website="https://chez-alice.fr"))["eligible"] == decide(lead())["eligible"] is True


def test_each_required_part_missing_is_named_and_the_prospect_waits_to_be_enriched():
    assert decide(lead(email=None))["missing_fields"] == ["email_missing"]
    assert decide(lead(email="nope"))["missing_fields"] == ["email_invalid"]
    assert decide(lead(email="a@example.com"))["missing_fields"] == ["email_invalid"]
    assert decide(lead(phone=""))["missing_fields"] == ["phone_missing"]
    assert decide(lead(phone="123"))["missing_fields"] == ["phone_invalid"]
    assert decide(sources=[source(fields={"lat": 48.5, "lon": -2.7})])["missing_fields"] == ["address_missing"]
    assert decide(sources=[source(fields={"address": "12 rue du Port"})])["missing_fields"] == ["coordinates_missing"]
    out = decide(sources=[])
    assert out["status"] == "to_enrich" and "source_missing" in out["missing_fields"] and not out["eligible"]


def test_freshness_of_the_source_and_of_the_fit_score_is_required():
    assert decide(sources=[source(fetched_at=NOW - timedelta(days=45))])["missing_fields"] == ["source_stale"]
    assert decide(lead(qualification_scored_at=NOW - timedelta(days=45)))["missing_fields"] == ["fit_stale"]
    assert decide(lead(fit_score=10))["missing_fields"] == ["fit_low"]
    assert decide(lead(fit_score=None, qualification_scored_at=None))["missing_fields"] == ["fit_missing"]


def test_malformed_json_in_a_source_is_a_gap_never_an_error():
    out = decide(sources=[source(fields={"address": 12, "lat": "48.5", "lon": None})])
    assert out["missing_fields"] == ["address_missing", "coordinates_missing"]
    assert decide(sources=[source(fields="oops")])["missing_fields"] == ["address_missing", "coordinates_missing"]
    assert (
        not policy.coordinates_ok(True, True) and not policy.coordinates_ok(0, 0) and not policy.coordinates_ok(91, 0)
    )


def test_blocked_records_are_excluded_not_to_enrich():
    assert decide(suppressed=True)["reasons"] == ["suppressed"]
    assert decide(opted_out=True)["reasons"] == ["opted_out"]
    assert decide(lead(review_status="rejected"))["reasons"] == ["rejected"]
    demo = decide(sources=[source(), source(id="s2", source_name="fixture_directory")])
    assert demo["status"] == "excluded" and demo["reasons"] == ["demo_data"] and not demo["eligible"]


def intent(**over):
    base = {
        "signal_key": "commercial_intent",
        "state": "detected",
        "evidence": "Asked for a quote on the contact page",
        "source_id": "s1",
        "created_at": NOW - timedelta(days=2),
    }
    return {**base, **over}


def test_hot_needs_a_recent_detected_evidenced_intent_linked_to_a_real_source():
    assert decide(signals=[intent()])["is_hot"] and decide(signals=[intent()])["priority_label"].startswith("Hot")
    for bad in (
        intent(evidence=" "),
        intent(state="unknown"),
        intent(source_id="elsewhere"),
        intent(created_at=NOW - timedelta(days=90)),
        intent(signal_key="no_website"),  # a need, not a purchase intent
    ):
        assert decide(signals=[bad])["is_hot"] is False
    assert decide(lead(email=None), signals=[intent()])["is_hot"] is False  # never hot without being qualified
