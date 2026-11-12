"""The e-mail flow, offline: which provider carries a message, what an ambiguous outcome means, who a sandbox really
restricts, whether the worker agrees with the API, and whether every task has a queue somebody consumes.

Nothing here opens a network connection or sends anything: the SMTP adapter, Redis and Celery are replaced.
"""

import importlib
import json
import re
import secrets
from pathlib import Path
from types import SimpleNamespace

import pytest

from celery_app import celery_app
from repositories import outreach_repo
from services import mail_provider, runtime_config, sendgrid_svc, smtp_svc
from services.integrations_status import Facts, build
from services.outreach_os import channels
from services.outreach_os import sandbox as sandbox_rules

CONSUMED = {"sends", "automation", "webhooks"}  # what the worker (render.yaml, embedded_worker.sh) listens to
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in (
        "FEATURE_LIVE_SENDING", "SEND_KILL_SWITCH", "OUTREACH_SANDBOX", "OUTREACH_LIVE_ALLOWLIST", "OUTREACH_TEST_SINK",
        "APP_ENV", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_SECURITY", "OUTREACH_SENDER_NAME",
        "OUTREACH_SENDER_COMPANY", "OUTREACH_SENDER_ADDRESS", "OUTREACH_SENDER_EMAIL",
    ):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sendgrid_svc, "API_KEY", None)
    monkeypatch.setattr(sendgrid_svc, "FROM_EMAIL", None)


def _smtp_env(monkeypatch, *, host="smtp.hostinger.com"):
    monkeypatch.setenv("SMTP_HOST", host)
    monkeypatch.setenv("SMTP_USERNAME", "founder@plantiers.example")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))  # generated per run: never a literal credential
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    for key, value in (
        ("OUTREACH_SENDER_NAME", "Plantiers"),
        ("OUTREACH_SENDER_COMPANY", "Plantiers SAS"),
        ("OUTREACH_SENDER_ADDRESS", "1 rue Fictive, 69000 Lyon"),
        ("OUTREACH_SENDER_EMAIL", "founder@plantiers.example"),
    ):
        monkeypatch.setenv(key, value)


class FakeSmtp:
    """Stands in for the SMTP adapter: records what it was asked and answers as scripted."""

    channel, name, dry_run = "email", "smtp", False

    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def send(self, message):
        self.calls.append(message)
        return self.outcome


# ---------------------------------------------------------------- which provider carried the message
def test_smtp_carries_the_message_without_sendgrid_and_the_result_names_smtp(monkeypatch):
    _smtp_env(monkeypatch)
    fake = FakeSmtp(channels.SendResult("sent", "id-1@plantiers.example", simulated=False))
    monkeypatch.setattr(smtp_svc, "adapter_from_env", lambda *a, **k: fake)
    assert mail_provider.email_provider() == "smtp"  # SendGrid is absent and not needed
    out = mail_provider.send_email(
        "a@b.example", "Sujet", "Corps", headers={"List-Unsubscribe": "<mailto:x@y.example>"}
    )
    assert out["status"] == "sent" and out["provider"] == "smtp" and out["ambiguous"] is False
    assert len(fake.calls) == 1 and fake.calls[0].to == "a@b.example"  # one message, one recipient


def test_a_record_never_claims_sendgrid_for_a_message_smtp_carried_nor_for_one_nobody_carried(monkeypatch):
    out = mail_provider.send_email("a@b.example", "s", "b")  # nothing configured
    assert out["status"] == "failed" and out["provider"] is None
    monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    assert mail_provider.send_email("a@b.example", "s", "b")["provider"] is None


def test_the_sink_names_itself(monkeypatch):
    monkeypatch.setenv("OUTREACH_TEST_SINK", "true")
    out = mail_provider.send_email("a@b.example", "s", "b")
    assert out["provider"] == "sink" and out["provider_id"].startswith("sink:")


def test_an_outcome_the_server_may_have_accepted_is_flagged_ambiguous_and_a_refusal_is_not(monkeypatch):
    _smtp_env(monkeypatch)
    lost = FakeSmtp(
        channels.SendResult("unknown", None, "connection lost while sending (OSError): outcome unknown", False)
    )
    monkeypatch.setattr(smtp_svc, "adapter_from_env", lambda *a, **k: lost)
    ambiguous = mail_provider.send_email("a@b.example", "s", "b")
    assert ambiguous["status"] == "failed" and ambiguous["ambiguous"] is True
    assert outreach_repo.AMBIGUOUS_MARK in ambiguous["error"]
    refused = FakeSmtp(channels.SendResult("failed", None, "the server refused the recipient address", False))
    monkeypatch.setattr(smtp_svc, "adapter_from_env", lambda *a, **k: refused)
    assert mail_provider.send_email("a@b.example", "s", "b")["ambiguous"] is False


# ---------------------------------------------------------------- when a step may start again by itself
def _attempt(status, error=None):
    return SimpleNamespace(status=status, error=error)


@pytest.mark.parametrize(
    "attempt,blocks",
    [
        (None, False),  # nothing recorded: first attempt
        (_attempt("failed", "the server refused the recipient address"), False),  # definitive refusal: may start again
        (_attempt("failed", "connection lost while sending (OSError): outcome unknown"), True),  # may have left
        (_attempt("queued"), True),  # the marker written before the provider call, no outcome after it
        (_attempt("sent"), True),
        (_attempt("delivered"), True),
        (_attempt("replied"), True),
        (_attempt("bounced"), True),
    ],
)
def test_only_a_definitive_refusal_or_no_record_lets_a_step_start_again(attempt, blocks):
    assert outreach_repo.attempt_blocks_resend(attempt) is blocks


# ---------------------------------------------------------------- who a sandbox really restricts
@pytest.mark.parametrize(
    "live,sandbox,entries,code",
    [
        (False, True, 2, "dry_run"),
        (False, False, 2, "dry_run"),
        (True, True, 0, "sandbox_empty"),
        (True, True, 2, "sandbox_allowlist"),
        (True, False, 2, "allowlist_inactive"),  # the owner's snapshot: sandbox off, 2 entries restrict nobody
        (True, False, 0, "open"),
    ],
)
def test_the_allowlist_only_restricts_while_the_sandbox_is_on_and_the_sentence_says_so(live, sandbox, entries, code):
    got, sentence = sandbox_rules.scope(live=live, sandbox_on=sandbox, entries=entries)
    assert got == code and sentence
    if code == "allowlist_inactive":
        assert "INACTIVE" in sentence and "ne restreint personne" in sentence
    if code in ("open", "allowlist_inactive"):
        assert "partira réellement" in sentence


def test_the_adapter_enforces_the_allowlist_only_when_the_sandbox_is_on(monkeypatch):
    _smtp_env(monkeypatch)
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", "founder@plantiers.example, @team.example")
    monkeypatch.setenv("OUTREACH_SANDBOX", "true")
    on = smtp_svc.adapter_from_env()
    assert on._allowlist == ("founder@plantiers.example", "@team.example")
    refused = on.send(
        channels.ChannelMessage(
            "stranger@else.example", "s", "b", "n", "founder@plantiers.example", "k", {"List-Unsubscribe": "<x>"}
        )
    )
    assert refused.status == "failed" and "allowlist" in refused.error  # nothing left: refused before any connection
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    assert smtp_svc.adapter_from_env()._allowlist is None  # the two entries restrict nobody any more


def test_the_integration_status_states_that_the_allowlist_is_not_applied_with_the_sandbox_off():
    live = Facts(
        live_sending=True, smtp_configured=True, smtp_host="smtp.hostinger.com", sandbox=False, allowlist_size=2
    )
    item = {i["id"]: i for i in build(live)["items"]}["sending_mode"]
    assert item["label"] == "LIVE · REAL E-MAIL"
    assert "NOT applied" in item["summary"]
    assert any("INACTIVE" in value for _, value in item["facts"])


# ---------------------------------------------------------------- the worker must agree with the API
def test_the_fingerprint_is_booleans_names_and_counts_never_a_secret(monkeypatch):
    _smtp_env(monkeypatch)
    password = smtp_svc.SmtpConfig.from_env().password
    fp = runtime_config.fingerprint()
    assert set(fp) == set(runtime_config.KEYS)
    assert fp["provider"] == "smtp" and fp["smtp_host"] == "smtp.hostinger.com" and fp["live"] is True
    assert password not in json.dumps(fp) and "founder@plantiers.example" not in json.dumps(fp)


def test_a_difference_between_the_api_and_the_worker_is_reported_by_name():
    api = {
        "live": True,
        "sandbox": False,
        "kill_switch": False,
        "provider": "smtp",
        "smtp_host": "h",
        "sender_configured": True,
        "allowlist_size": 2,
        "test_sink": False,
    }
    assert runtime_config.drift(api, dict(api)) == []
    worker = {**api, "live": False, "provider": None}
    assert runtime_config.drift(api, worker) == ["live", "provider"]
    assert runtime_config.drift(api, {k: v for k, v in api.items() if k != "sandbox"}) == ["sandbox"]  # not reported
    text = runtime_config.drift_text(["live", "provider"])
    assert "FEATURE_LIVE_SENDING" in text and "alignez" in text and runtime_config.drift_text([]) == ""


def test_the_worker_publishes_its_configuration_in_the_beat_heartbeat_without_any_secret(monkeypatch):
    from tasks import health_tasks

    _smtp_env(monkeypatch)
    stored = {}

    class FakeRedis:
        @classmethod
        def from_url(cls, *a, **k):
            return cls()

        def set(self, key, value, ex=None):
            stored[key] = value

        def close(self):
            pass

    monkeypatch.setattr(health_tasks.redis, "Redis", FakeRedis)
    assert health_tasks.record_beat_heartbeat() is True
    payload = json.loads(stored[health_tasks.WORKER_CONFIG_KEY])
    assert set(payload) == set(runtime_config.KEYS) | {"reported_at"}
    assert smtp_svc.SmtpConfig.from_env().password not in stored[health_tasks.WORKER_CONFIG_KEY]
    assert health_tasks.BEAT_HEARTBEAT_KEY in stored


# ---------------------------------------------------------------- every task has a queue somebody consumes
def _load_tasks():
    for module in (
        "automation",
        "campaign",
        "health",
        "inbox",
        "mandate",
        "prospecting",
        "qualification",
        "send",
        "webhook",
    ):
        importlib.import_module(f"tasks.{module}_tasks")


def test_every_task_routes_to_a_queue_the_worker_consumes():
    _load_tasks()

    ours = [name for name in celery_app.tasks if name.startswith("tasks.")]
    assert len(ours) >= 10
    unrouted = []
    for name in ours:
        queue = celery_app.amqp.router.route({}, name)["queue"].name
        if queue not in CONSUMED:
            unrouted.append((name, queue))
    assert unrouted == []  # a task sent to the default queue would wait forever: nobody listens there


def test_every_beat_entry_targets_a_consumed_queue_and_a_registered_task():
    _load_tasks()

    for key, entry in celery_app.conf.beat_schedule.items():
        assert entry["task"] in celery_app.tasks, key
        assert entry["options"]["queue"] in CONSUMED, key
    assert "send-due-campaign-messages" in celery_app.conf.beat_schedule  # the individual campaigns' sender
    assert "run-automation-mandates" in celery_app.conf.beat_schedule  # the bounded automatic mode (no-op while off)


def test_the_deployed_worker_and_the_embedded_worker_consume_exactly_those_queues():
    render = (ROOT / "render.yaml").read_text()
    command = re.search(r"dockerCommand: (celery -A celery_app worker[^\n]*)", render).group(1)
    assert set(re.search(r"-Q (\S+)", command).group(1).split(",")) == CONSUMED
    embedded = (ROOT / "backend" / "embedded_worker.sh").read_text()
    assert set(re.search(r"EMBEDDED_WORKER_QUEUES:-([a-z,]+)", embedded).group(1).split(",")) == CONSUMED
