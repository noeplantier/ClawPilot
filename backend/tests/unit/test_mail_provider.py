"""The provider chain behind every legacy send path, offline: nothing is sent, nothing is faked as sent."""

import pytest

from services import feature_flags, mail_provider, send_gate, sendgrid_svc, smtp_svc, twilio_svc
from services.outreach_os import channels


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in (
        "FEATURE_LIVE_SENDING", "SEND_KILL_SWITCH", "OUTREACH_SANDBOX", "OUTREACH_LIVE_ALLOWLIST",
        "OUTREACH_LIVE_PHONES", "OUTREACH_TEST_SINK", "APP_ENV", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD",
        "OUTREACH_SENDER_NAME", "OUTREACH_SENDER_COMPANY", "OUTREACH_SENDER_ADDRESS", "OUTREACH_SENDER_EMAIL",
    ):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sendgrid_svc, "API_KEY", None)
    monkeypatch.setattr(sendgrid_svc, "FROM_EMAIL", None)
    monkeypatch.setattr(twilio_svc, "SID", None)
    monkeypatch.setattr(twilio_svc, "TOKEN", None)


def test_nothing_configured_is_a_failure_that_says_what_to_set_never_a_sent_status():
    email = mail_provider.send_email("a@b.example", "s", "b")
    assert email["status"] == "failed" and email["provider_id"] is None
    assert "SMTP_HOST" in email["error"] and "SENDGRID_API_KEY" in email["error"]
    monkeypatch_free = mail_provider.send_whatsapp("+33612345678", "hi")
    assert monkeypatch_free["status"] == "failed" and monkeypatch_free["provider_id"] is None


def test_sendgrid_without_credentials_and_with_a_rejecting_provider_both_fail_honestly(monkeypatch):
    assert sendgrid_svc.send_email("a@b.example", "s", "b")["status"] == "failed"
    monkeypatch.setattr(sendgrid_svc, "API_KEY", "k-" + "x" * 10)
    monkeypatch.setattr(sendgrid_svc, "FROM_EMAIL", "founder@plantiers.com")

    class Boom:
        def __init__(self, key):
            raise RuntimeError("The from address does not match a verified Sender Identity")

    import sendgrid

    monkeypatch.setattr(sendgrid, "SendGridAPIClient", Boom)
    out = sendgrid_svc.send_email("a@b.example", "s", "b")
    assert out["status"] == "failed" and "verified Sender Identity" in out["error"]  # the real reason, not a "mock"


def test_the_provider_for_a_channel_follows_the_configuration(monkeypatch):
    assert mail_provider.provider_for("email") is None and mail_provider.provider_for("whatsapp") is None
    monkeypatch.setattr(sendgrid_svc, "API_KEY", "k-" + "x" * 10)
    monkeypatch.setattr(sendgrid_svc, "FROM_EMAIL", "founder@plantiers.com")
    assert mail_provider.provider_for("email") == "sendgrid"
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_USERNAME", "u@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "pw-" + "x" * 10)
    assert mail_provider.provider_for("email") == "sendgrid"  # SMTP needs live sending on
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    assert mail_provider.provider_for("email") == "smtp"  # and then it comes first


def test_the_gate_refuses_a_legacy_path_without_a_provider_but_not_a_path_that_brings_its_own():
    with pytest.raises(send_gate.SendBlocked) as raised:
        send_gate.assert_provider_configured("email")
    assert raised.value.code == "provider_not_configured"
    with pytest.raises(send_gate.SendBlocked):
        send_gate.assert_provider_configured("whatsapp")


def test_the_test_sink_records_a_clearly_labelled_non_send_and_never_runs_in_production(monkeypatch):
    monkeypatch.setenv("OUTREACH_TEST_SINK", "true")
    assert feature_flags.test_sink() is True
    out = mail_provider.send_email("a@b.example", "s", "b")
    assert out["status"] == "sent" and out["provider_id"].startswith("sink:")
    assert mail_provider.send_whatsapp("+33612345678", "hi")["provider_id"].startswith("sink:")
    monkeypatch.setenv("APP_ENV", "production")  # a real deployment can never record a send that did not happen
    assert feature_flags.test_sink() is False
    assert mail_provider.send_email("a@b.example", "s", "b")["status"] == "failed"


def test_the_kill_switch_stops_every_provider(monkeypatch):
    monkeypatch.setenv("OUTREACH_TEST_SINK", "true")
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    assert mail_provider.send_email("a@b.example", "s", "b")["status"] == "failed"
    assert mail_provider.send_whatsapp("+33612345678", "hi")["status"] == "failed"


class FakeAdapter:
    name = "fake_smtp"
    dry_run = False

    def __init__(self, status="sent", error=None):
        self.status, self.error, self.seen = status, error, []

    def send(self, message: channels.ChannelMessage):
        self.seen.append(message)
        return channels.SendResult(
            self.status, "<id@x>" if self.status == "sent" else None, self.error, simulated=False
        )


def _identity(monkeypatch):
    monkeypatch.setenv("OUTREACH_SENDER_NAME", "Noé")
    monkeypatch.setenv("OUTREACH_SENDER_COMPANY", "Plantiers")
    monkeypatch.setenv("OUTREACH_SENDER_ADDRESS", "1 rue Fictive, 69000 Lyon")
    monkeypatch.setenv("OUTREACH_SENDER_EMAIL", "founder@plantiers.com")


def test_the_smtp_path_sends_through_the_adapter_and_reports_a_refusal_as_a_failure(monkeypatch):
    _identity(monkeypatch)
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_USERNAME", "u@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "pw-" + "x" * 10)
    adapter = FakeAdapter()
    monkeypatch.setattr(smtp_svc, "adapter_from_env", lambda extra_allowed=(): adapter)
    ok = mail_provider.send_email("founder@plantiers.com", "Test", "Body", headers={"List-Unsubscribe": "<mailto:x>"})
    assert ok == {"status": "sent", "provider_id": "<id@x>", "error": None}
    assert adapter.seen[0].to == "founder@plantiers.com" and adapter.seen[0].sender_email == "founder@plantiers.com"
    refused = FakeAdapter("failed", "the sandbox refuses this recipient")
    monkeypatch.setattr(smtp_svc, "adapter_from_env", lambda extra_allowed=(): refused)
    out = mail_provider.send_email("someone@else.example", "Test", "Body")
    assert out["status"] == "failed" and "sandbox" in out["error"]
    unknown = FakeAdapter("unknown", "connection lost while sending: outcome unknown")
    monkeypatch.setattr(smtp_svc, "adapter_from_env", lambda extra_allowed=(): unknown)
    assert mail_provider.send_email("founder@plantiers.com", "T", "B")["status"] == "failed"  # never claimed as sent


def test_whatsapp_in_the_sandbox_only_reaches_the_listed_numbers(monkeypatch):
    monkeypatch.setattr(twilio_svc, "SID", "AC" + "0" * 32)
    monkeypatch.setattr(twilio_svc, "TOKEN", "tok-" + "x" * 10)
    out = twilio_svc.send_whatsapp("+33612345678", "hi")
    assert out["status"] == "failed" and "OUTREACH_LIVE_PHONES" in out["error"]  # sandbox on by default, empty list
    monkeypatch.setenv("OUTREACH_LIVE_PHONES", "+33666167788")
    assert feature_flags.live_phones() == ("+33666167788",)
    called = []

    class Client:
        def __init__(self, sid, token):
            self.messages = self

        def create(self, **kw):
            called.append(kw)
            return type("M", (), {"sid": "SM123"})()

    import twilio.rest

    monkeypatch.setattr(twilio.rest, "Client", Client)
    assert twilio_svc.send_whatsapp("+33612345678", "hi")["status"] == "failed"  # still not listed
    ok = twilio_svc.send_whatsapp("0666167788", "hi")  # national format is normalised to the listed number
    assert ok == {"status": "sent", "provider_id": "SM123", "error": None}
    assert called[0]["to"] == "whatsapp:+33666167788"


def test_live_phones_drops_what_cannot_be_read_and_normalises_the_rest(monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_PHONES", "+33666167788, 0612345678; nonsense, +33666167788")
    assert feature_flags.live_phones() == ("+33666167788", "+33612345678")
