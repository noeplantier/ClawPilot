"""The Brevo adapter, offline: the HTTP call is replaced by a recorder, no request ever leaves.

Real delivery through Brevo is NOT exercised here (it needs a real key and a network): these tests pin the request
(one recipient, plain text, unsubscribe headers), the classification of answers, and the secrecy of the key.
"""

import logging
import secrets

import pytest
import requests

from services import brevo_svc, mail_provider
from services.outreach_os.channels import ChannelMessage, unsubscribe_headers

KEY = secrets.token_hex(16)  # generated per run: never a literal credential in the repository


class Answer:
    def __init__(self, status=201, body=None):
        self.status_code = status
        self._body = {"messageId": "<abc@smtp-relay.mailin.fr>"} if body is None else body

    def json(self):
        return self._body


class Recorder:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", KEY)
    for name in ("OUTREACH_SANDBOX", "OUTREACH_LIVE_ALLOWLIST", "OUTREACH_TEST_SINK", "SMTP_HOST", "SMTP_USERNAME"):
        monkeypatch.delenv(name, raising=False)


def message(**kw):
    base = dict(
        to="prospect@restaurant.example",
        subject="Votre site, Chez Marcel",
        body="Bonjour Marcel,\n\nUn site rapide.\n\n—\nSe désinscrire : https://api.example/api/unsubscribe/t0k",
        sender_name="Noé — Plantiers",
        sender_email="founder@plantiers.com",
        idempotency_key="k1",
        headers=unsubscribe_headers("https://api.example/api/unsubscribe/t0k"),
    )
    base.update(kw)
    return ChannelMessage(**base)


def adapter(reply, allowlist=None):
    post = Recorder(reply)
    return brevo_svc.BrevoEmailAdapter(brevo_svc.BrevoConfig(KEY), allowlist, post=post), post


def test_one_message_goes_to_one_recipient_in_plain_text_with_the_unsubscribe_headers():
    a, post = adapter(Answer())
    result = a.send(message())
    assert result.status == "sent" and result.provider_id == "<abc@smtp-relay.mailin.fr>" and not result.simulated
    (call,) = post.calls
    assert call["url"] == "https://api.brevo.com/v3/smtp/email"
    assert (
        call["headers"]["api-key"] == KEY and call["allow_redirects"] is False and call["timeout"] == brevo_svc.TIMEOUT
    )
    body = call["json"]
    assert body["to"] == [{"email": "prospect@restaurant.example"}]
    assert body["sender"] == {"name": "Noé — Plantiers", "email": "founder@plantiers.com"}
    assert body["textContent"].endswith("/api/unsubscribe/t0k") and "htmlContent" not in body
    assert body["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


@pytest.mark.parametrize(
    "msg,words",
    [
        (message(to="a@x.example, b@x.example"), "one recipient"),
        (message(to="not-an-address"), "invalid recipient"),
        (message(headers={}), "List-Unsubscribe"),
        (message(body="  "), "empty"),
        (message(sender_email="nobody"), "sender address"),
    ],
)
def test_a_message_that_breaks_a_rule_never_reaches_brevo(msg, words):
    a, post = adapter(Answer())
    result = a.send(msg)
    assert result.status == "failed" and words in result.error and post.calls == []


def test_the_sandbox_refuses_a_recipient_outside_the_allowlist_before_any_request():
    a, post = adapter(Answer(), allowlist=("founder@plantiers.com",))
    assert a.send(message()).error == "recipient is not on the sandbox allowlist" and post.calls == []
    assert a.send(message(to="founder@plantiers.com")).status == "sent"


@pytest.mark.parametrize(
    "status,words",
    [(401, "BREVO_API_KEY"), (400, "not be verified"), (402, "quota"), (429, "limit"), (503, "nothing was resent")],
)
def test_a_refusal_is_failed_with_the_reason_and_neither_the_key_nor_the_body_is_logged(status, words, caplog):
    echoed = {"message": "prospect@restaurant.example " + KEY}
    a, _ = adapter(Answer(status, echoed))
    with caplog.at_level(logging.WARNING):
        result = a.send(message())
    assert result.status == "failed" and words in result.error
    assert KEY not in result.error and "prospect@" not in result.error
    assert KEY not in caplog.text and "prospect@" not in caplog.text and f"HTTP {status}" in caplog.text


def test_a_lost_answer_after_sending_is_unknown_never_resent_and_a_closed_door_is_failed():
    a, _ = adapter(requests.ReadTimeout("read timed out"))
    assert a.send(message()).status == "unknown"
    a, _ = adapter(requests.ConnectTimeout("connect timed out"))
    assert a.send(message()).status == "failed"
    a, _ = adapter(requests.ConnectionError("Failed to establish a new connection: [Errno 111] Connection refused"))
    assert a.send(message()).status == "failed"
    a, _ = adapter(requests.ConnectionError("Connection aborted. RemoteDisconnected"))
    assert a.send(message()).status == "unknown"


def test_the_key_is_never_in_the_repr_and_a_missing_key_means_no_adapter(monkeypatch):
    assert KEY not in repr(brevo_svc.BrevoConfig(KEY))
    monkeypatch.delenv("BREVO_API_KEY")
    assert not brevo_svc.is_configured() and brevo_svc.adapter_from_env() is None


def test_brevo_is_chosen_before_smtp_when_live_and_the_sandbox_still_applies(monkeypatch):
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.hostinger.com")
    monkeypatch.setenv("SMTP_USERNAME", "founder@plantiers.com")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", "founder@plantiers.com")
    assert mail_provider.email_provider() == "brevo"
    live = mail_provider.live_adapter()
    assert live.name == "brevo" and live._allowlist == ("founder@plantiers.com",)  # sandbox is on by default
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    assert mail_provider.live_adapter()._allowlist is None
    monkeypatch.delenv("BREVO_API_KEY")
    assert mail_provider.email_provider() == "smtp" and mail_provider.live_adapter().name == "smtp"
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "false")
    monkeypatch.setenv("BREVO_API_KEY", KEY)
    assert mail_provider.email_provider() != "brevo"  # dry-run: no real channel is named
