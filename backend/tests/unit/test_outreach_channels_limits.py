"""Channel adapter, send limits, reply classification, kill switch — offline and deterministic."""

import socket
from datetime import datetime, timedelta, timezone

import pytest

from services import feature_flags, sendgrid_svc, twilio_svc
from services.outreach_os.channels import (
    ChannelMessage,
    DryRunEmailAdapter,
    LiveSendingNotAvailable,
    find_unsubscribe_url,
    select_adapter,
    unsubscribe_headers,
)
from services.outreach_os.limits import SendLimits, evaluate
from services.outreach_os.replies import is_opt_out

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
DAY_END = datetime(2026, 6, 2, 0, 0, tzinfo=UTC)


def msg(**kw):
    base = dict(
        to="a@b.example",
        subject="Hello",
        body="Body",
        sender_name="S",
        sender_email="s@x.example",
        idempotency_key="k1",
        headers=unsubscribe_headers("https://app.example/api/unsubscribe/tok"),
    )
    return ChannelMessage(**{**base, **kw})


# ---- adapter -------------------------------------------------------------------------------------------
def test_dry_run_adapter_is_deterministic_and_never_touches_the_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    adapter = DryRunEmailAdapter()
    first, second = adapter.send(msg()), adapter.send(msg())
    assert first == second and first.status == "sent" and first.provider_id.startswith("dryrun-") and first.simulated
    assert adapter.dry_run and adapter.send(msg(idempotency_key="k2")).provider_id != first.provider_id


@pytest.mark.parametrize(
    "kw,error",
    [
        ({"to": "not-an-email"}, "invalid recipient"),
        ({"subject": "  "}, "empty subject or body"),
        ({"body": ""}, "empty subject or body"),
        ({"headers": {}}, "List-Unsubscribe"),
    ],
)
def test_dry_run_adapter_rejects_malformed_messages(kw, error):
    result = DryRunEmailAdapter().send(msg(**kw))
    assert result.status == "failed" and error in result.error


def test_unsubscribe_headers_follow_rfc_8058():
    headers = unsubscribe_headers("https://app.example/api/unsubscribe/tok")
    assert headers["List-Unsubscribe"] == "<https://app.example/api/unsubscribe/tok>"
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_find_unsubscribe_url_in_a_body():
    body = "x\nPour ne plus recevoir de messages : https://app.example/api/unsubscribe/abc.def.\nfin"
    assert find_unsubscribe_url(body) == "https://app.example/api/unsubscribe/abc.def"
    assert find_unsubscribe_url("no link") is None


def test_live_sending_without_a_real_adapter_fails_closed():
    assert isinstance(select_adapter("email", live_sending_enabled=False), DryRunEmailAdapter)
    with pytest.raises(LiveSendingNotAvailable):
        select_adapter("email", live_sending_enabled=True)
    with pytest.raises(LiveSendingNotAvailable):
        select_adapter("whatsapp", live_sending_enabled=False)


# ---- limits --------------------------------------------------------------------------------------------
LIMITS = SendLimits(max_per_day=3, max_per_hour=2, min_delay_seconds=60)


def ago(**kw):
    return NOW - timedelta(**kw)


def test_first_message_is_allowed():
    assert evaluate(LIMITS, [], NOW, DAY_END).allowed


def test_minimum_delay_boundary():
    blocked = evaluate(LIMITS, [ago(seconds=59)], NOW, DAY_END)
    assert (
        not blocked.allowed and blocked.code == "delay" and blocked.retry_at == ago(seconds=59) + timedelta(seconds=60)
    )
    assert evaluate(LIMITS, [ago(seconds=60)], NOW, DAY_END).allowed
    assert evaluate(SendLimits(3, 2, 0), [ago(seconds=1)], NOW, DAY_END).allowed  # 0 disables the delay


def test_hourly_limit_is_rolling_and_reports_when_it_frees_up():
    sent = [ago(minutes=50), ago(minutes=10)]
    d = evaluate(LIMITS, sent, NOW, DAY_END)
    assert not d.allowed and d.code == "hourly" and d.retry_at == ago(minutes=50) + timedelta(hours=1)
    assert evaluate(LIMITS, [ago(minutes=61), ago(minutes=10)], NOW, DAY_END).allowed  # first one left the window


def test_daily_limit_blocks_until_the_end_of_the_day_and_wins_over_the_others():
    sent = [ago(hours=5), ago(hours=4), ago(hours=3)]
    d = evaluate(LIMITS, sent, NOW, DAY_END)
    assert not d.allowed and d.code == "daily" and d.retry_at == DAY_END
    assert evaluate(LIMITS, sent[:2], NOW, DAY_END).allowed


def test_zero_limits_block_everything():
    assert evaluate(SendLimits(0, 5, 0), [], NOW, DAY_END).code == "daily"
    zero_hour = evaluate(SendLimits(5, 0, 0), [], NOW, DAY_END)
    assert not zero_hour.allowed and zero_hour.code == "hourly" and zero_hour.retry_at == DAY_END


# ---- reply classification ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "STOP",
        "Stop.",
        "  stop  ",
        "stop svp",
        "STOP please",
        "Unsubscribe",
        "Désinscription",
        "Merci de me désinscrire",
        "Je ne souhaite plus recevoir vos messages",
        "ne plus recevoir",
        "Please remove me from your list",
        "Ne me contactez plus",
    ],
)
def test_opt_out_replies_are_detected(text):
    assert is_opt_out(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Bonjour, oui pourquoi pas",
        "Non-stop activité chez nous",
        "Please do not stop by tomorrow",
        "Stop by tomorrow at 10",
        "Intéressé, rappelez-moi",
        "Pouvez-vous m'envoyer un devis ?",
    ],
)
def test_ordinary_replies_are_not_opt_outs(text):
    assert not is_opt_out(text)


# ---- kill switch ----------------------------------------------------------------------------------------
def test_kill_switch_defaults_off_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv("SEND_KILL_SWITCH", raising=False)
    assert not feature_flags.kill_switch() and feature_flags.snapshot()["kill_switch"] is False
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    assert feature_flags.kill_switch() and feature_flags.snapshot()["kill_switch"] is True
    monkeypatch.setenv("SEND_KILL_SWITCH", "nope")
    assert not feature_flags.kill_switch()


def test_kill_switch_stops_legacy_providers_before_any_client_is_built(monkeypatch):
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    monkeypatch.setattr(sendgrid_svc, "API_KEY", "SG.fake-key-for-test")
    monkeypatch.setattr(twilio_svc, "SID", "ACfake")
    monkeypatch.setattr(twilio_svc, "TOKEN", "fake")

    def boom(*a, **k):
        raise AssertionError("a provider client was built while the kill switch is on")

    monkeypatch.setattr("sendgrid.SendGridAPIClient", boom)
    monkeypatch.setattr("twilio.rest.Client", boom)
    email = sendgrid_svc.send_email("a@b.example", "s", "b")
    wa = twilio_svc.send_whatsapp("+33123456789", "b")
    assert email["status"] == "failed" and "kill switch" in email["error"]
    assert wa["status"] == "failed" and "kill switch" in wa["error"]
