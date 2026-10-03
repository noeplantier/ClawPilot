"""Drafts only state evidence-backed facts; compliance gate; unsubscribe tokens; feature flags."""

import uuid
from datetime import date

import pytest

from services import feature_flags
from services.outreach_os import signals as sig
from services.outreach_os.drafts import SenderIdentity, compliance_problems, render_email_draft
from services.outreach_os.types import SignalResult, SignalState
from services.outreach_os.unsubscribe import make_token, parse_token

SENDER = SenderIdentity("Jeanne Test", "Exemple SAS", "1 rue Fictive, 69000 Lyon", "jeanne@exemple.example")
URL = "https://app.example/api/unsubscribe/tok"


def results(**states):
    return [SignalResult(k, SignalState(states.get(k, "unknown")), "e") for k in sig.ALL_SIGNALS]


def render(res, **kw):
    return render_email_draft(
        business_name="Chez Test",
        city="Lyon",
        results=res,
        source_name="Annuaire Fictif",
        last_updated=kw.get("last_updated"),
        sender=SENDER,
        unsubscribe_url=URL,
    )


def test_draft_states_only_detected_signals():
    d = render(
        results(
            **{sig.BOOKING_PAGE_MISSING: "detected", sig.NOT_MOBILE_FRIENDLY: "not_detected", sig.NO_WEBSITE: "unknown"}
        )
    )
    assert len(d.facts) == 1 and "réserver en ligne" in d.facts[0]
    assert "mobile" not in d.body.lower().split("cordialement")[0]
    assert "site web propre" not in d.body


def test_draft_with_no_facts_is_neutral_not_invented():
    d = render(results())
    assert d.facts == []
    assert "observations" not in d.body
    assert "Chez Test" in d.body


def test_stale_fact_needs_a_date():
    assert render(results(**{sig.STALE_LISTING: "detected"})).facts == []
    d = render(results(**{sig.STALE_LISTING: "detected"}), last_updated=date(2024, 1, 5))
    assert "05/01/2024" in d.facts[0]


def test_draft_contains_mandatory_elements_and_passes_compliance():
    d = render(results(**{sig.NO_WEBSITE: "detected"}))
    for needle in (SENDER.name, SENDER.company, SENDER.postal_address, "Annuaire Fictif", URL):
        assert needle in d.body
    assert compliance_problems(d.body, SENDER) == []


def test_compliance_accepts_http_dev_url_but_not_a_lookalike():
    d = render(results())
    assert compliance_problems(d.body.replace(URL, "http://localhost:8000/api/unsubscribe/tok"), SENDER) == []
    assert "missing working unsubscribe link" in compliance_problems(
        d.body.replace(URL, "https://evil.example/somewhere/else"), SENDER
    )


def test_compliance_flags_missing_elements():
    assert "missing postal address" in compliance_problems("Bonjour", SENDER)
    assert "missing data-origin statement" in compliance_problems("Bonjour", SENDER)
    assert "missing working unsubscribe link" in compliance_problems("Bonjour {{unsubscribe_url}}", SENDER)
    d = render(results())
    stripped = d.body.replace(URL, "{{unsubscribe_url}}")
    assert "missing working unsubscribe link" in compliance_problems(stripped, SENDER)


def test_sender_identity_never_defaulted(monkeypatch):
    for var in ("OUTREACH_SENDER_NAME", "OUTREACH_SENDER_COMPANY", "OUTREACH_SENDER_ADDRESS", "OUTREACH_SENDER_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    assert SenderIdentity.from_env() is None
    monkeypatch.setenv("OUTREACH_SENDER_NAME", "N")
    monkeypatch.setenv("OUTREACH_SENDER_COMPANY", "C")
    monkeypatch.setenv("OUTREACH_SENDER_ADDRESS", "A")
    assert SenderIdentity.from_env() is None  # still incomplete
    monkeypatch.setenv("OUTREACH_SENDER_EMAIL", "e@x.example")
    assert SenderIdentity.from_env() == SenderIdentity("N", "C", "A", "e@x.example")


# ---- unsubscribe tokens ---------------------------------------------------------------------------------
def test_token_roundtrip_and_tamper_detection():
    acc, lead = uuid.uuid4(), uuid.uuid4()
    token = make_token("s3cret", acc, lead)
    assert parse_token("s3cret", token) == (acc, lead)
    assert parse_token("other-secret", token) is None
    head, sig_part = token.rsplit(".", 1)
    assert parse_token("s3cret", head + "." + "0" * len(sig_part)) is None
    assert parse_token("s3cret", make_token("s3cret", acc, uuid.uuid4()).split(".")[0] + "." + sig_part) is None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b", "....", "%%%.%%%", "YQ.zz"])
def test_token_garbage_is_rejected_without_raising(garbage):
    assert parse_token("s3cret", garbage) is None


# ---- feature flags ----------------------------------------------------------------------------------------
def test_flags_are_off_by_default_and_dry_run_is_on(monkeypatch):
    for name in feature_flags.KNOWN_FLAGS:
        monkeypatch.delenv(f"FEATURE_{name.upper()}", raising=False)
    monkeypatch.delenv("SEND_KILL_SWITCH", raising=False)
    monkeypatch.delenv("OUTREACH_SANDBOX", raising=False)
    assert feature_flags.snapshot() == {
        "live_sending": False,
        "external_sources": False,
        "prospect_import": False,
        "dry_run": True,
        "kill_switch": False,
        "sandbox": True,
    }


@pytest.mark.parametrize(
    "value, expected", [("", True), ("true", True), ("garbage", True), ("false", False), ("0", False), ("OFF", False)]
)
def test_the_sandbox_is_on_unless_explicitly_switched_off(monkeypatch, value, expected):
    monkeypatch.setenv("OUTREACH_SANDBOX", value)
    assert feature_flags.sandbox() is expected


def test_flags_enable_explicitly_and_reject_unknown(monkeypatch):
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    assert feature_flags.is_enabled("live_sending") and not feature_flags.dry_run()
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "maybe")
    assert feature_flags.dry_run()  # anything but an explicit yes stays off
    with pytest.raises(KeyError):
        feature_flags.is_enabled("nonexistent")
