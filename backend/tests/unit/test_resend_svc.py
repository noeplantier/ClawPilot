"""The Resend adapter, offline: the HTTP call is replaced by a recorder, no request ever leaves.

Real delivery through Resend is NOT exercised here (it needs a real key and a network): these tests pin the request
(one recipient, plain text, unsubscribe headers), the classification of answers, and the secrecy of the key.
"""

import logging
import secrets

import pytest
import requests

from services import mail_provider, resend_svc
from services.outreach_os.channels import ChannelMessage, unsubscribe_headers

KEY = "re_" + secrets.token_hex(16)  # generated per run: never a literal credential in the repository


class Answer:
    def __init__(self, status=201, body=None):
        self.status_code = status
        self._body = {"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"} if body is None else body

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
    monkeypatch.setenv("RESEND_API_KEY", KEY)
    for name in (
        "OUTREACH_SANDBOX",
        "OUTREACH_LIVE_ALLOWLIST",
        "OUTREACH_TEST_SINK",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "BREVO_API_KEY",
    ):
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
    return resend_svc.ResendEmailAdapter(resend_svc.ResendConfig(KEY), allowlist, post=post), post


def test_one_message_goes_to_one_recipient_in_plain_text_with_the_unsubscribe_headers():
    a, post = adapter(Answer())
    result = a.send(message())
    assert (
        result.status == "sent"
        and result.provider_id == "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"
        and not result.simulated
    )
    (call,) = post.calls
    assert call["url"] == "https://api.resend.com/emails"
    assert (
        call["headers"]["Authorization"] == f"Bearer {KEY}"
        and call["allow_redirects"] is False
        and call["timeout"] == resend_svc.TIMEOUT
    )
    body = call["json"]
    assert body["to"] == ["prospect@restaurant.example"]
    assert body["from"] == "Noé — Plantiers <founder@plantiers.com>"
    assert body["reply_to"] == "founder@plantiers.com"
    assert body["text"].endswith("/api/unsubscribe/t0k") and "html" not in body
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
def test_a_message_that_breaks_a_rule_never_reaches_resend(msg, words):
    a, post = adapter(Answer())
    result = a.send(msg)
    assert result.status == "failed" and words in result.error and post.calls == []


def test_the_sandbox_refuses_a_recipient_outside_the_allowlist_before_any_request():
    a, post = adapter(Answer(), allowlist=("founder@plantiers.com",))
    assert a.send(message()).error == "recipient is not on the sandbox allowlist" and post.calls == []
    assert a.send(message(to="founder@plantiers.com")).status == "sent"


@pytest.mark.parametrize(
    "status,words",
    [(401, "RESEND_API_KEY"), (422, "not be verified"), (429, "daily quota"), (503, "nothing was resent")],
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
    assert KEY not in repr(resend_svc.ResendConfig(KEY))
    monkeypatch.delenv("RESEND_API_KEY")
    assert not resend_svc.is_configured() and resend_svc.adapter_from_env() is None


def test_resend_is_chosen_first_then_brevo_then_smtp_and_the_sandbox_still_applies(monkeypatch):
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-" + "0" * 16)
    monkeypatch.setenv("SMTP_HOST", "smtp.hostinger.com")
    monkeypatch.setenv("SMTP_USERNAME", "founder@plantiers.com")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", "founder@plantiers.com")
    assert mail_provider.email_provider() == "resend"
    live = mail_provider.live_adapter()
    assert live.name == "resend" and live._allowlist == ("founder@plantiers.com",)  # sandbox is on by default
    assert mail_provider.live_endpoint() == ("resend", "api.resend.com", 443)
    monkeypatch.delenv("RESEND_API_KEY")
    assert mail_provider.email_provider() == "brevo" and mail_provider.live_adapter().name == "brevo"
    monkeypatch.delenv("BREVO_API_KEY")
    assert mail_provider.live_adapter().name == "smtp"
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "false")
    monkeypatch.setenv("RESEND_API_KEY", KEY)
    assert mail_provider.email_provider() != "resend"  # dry-run: no real channel is named


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_starts_with_the_shared_words_that_stop_a_mandate(status):
    from services.outreach_os.channels import AUTH_FAILED

    result = adapter(Answer(status, {}))[0].send(message())
    assert result.status == "failed" and result.error.startswith(AUTH_FAILED)


@pytest.mark.parametrize("status", [422, 429, 503])
def test_a_refusal_that_is_not_about_the_key_never_reads_as_an_authentication_error(status):
    from services.outreach_os.channels import AUTH_FAILED

    assert not adapter(Answer(status, {}))[0].send(message()).error.startswith(AUTH_FAILED)


# ---- webhook signature (Svix scheme) ----------------------------------------------------------
def _secret():
    import base64
    import secrets

    return "whsec_" + base64.b64encode(secrets.token_bytes(24)).decode()  # random per run: no literal secret


def _signed(body, secret, msg_id="msg_1", stamp=1_700_000_000):
    import base64
    import hashlib
    import hmac

    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": str(stamp), "svix-signature": f"v1,{sig}"}


BODY = b'{"type":"email.bounced","data":{"email_id":"e1","to":["a@b.example"]}}'
NOW = 1_700_000_000


def test_a_valid_signature_is_accepted_among_several_entries():
    from services import resend_svc

    secret = _secret()
    headers = _signed(BODY, secret)
    headers["svix-signature"] = "v1,bm90LXRoaXMtb25l " + headers["svix-signature"]  # a rotated key: any entry may match
    assert resend_svc.verify_webhook(BODY, headers, secret, now=NOW + 30)


def test_a_forged_tampered_stale_or_incomplete_event_is_refused():
    from services import resend_svc

    secret = _secret()
    good = _signed(BODY, secret)
    assert not resend_svc.verify_webhook(BODY, _signed(BODY, _secret()), secret, now=NOW)  # another secret
    assert not resend_svc.verify_webhook(BODY.replace(b"e1", b"e2"), good, secret, now=NOW)  # body changed
    assert not resend_svc.verify_webhook(BODY, {**good, "svix-id": "msg_2"}, secret, now=NOW)  # id changed
    assert not resend_svc.verify_webhook(BODY, good, secret, now=NOW + resend_svc.WEBHOOK_TOLERANCE + 1)  # replayed
    assert not resend_svc.verify_webhook(BODY, good, secret, now=NOW - resend_svc.WEBHOOK_TOLERANCE - 1)  # ahead
    assert not resend_svc.verify_webhook(BODY, {**good, "svix-signature": good["svix-signature"][3:]}, secret, now=NOW)
    for missing in ("svix-id", "svix-timestamp", "svix-signature"):
        assert not resend_svc.verify_webhook(BODY, {k: v for k, v in good.items() if k != missing}, secret, now=NOW)
    assert not resend_svc.verify_webhook(BODY, good, "", now=NOW)
    assert not resend_svc.verify_webhook(BODY, good, "whsec_not base64!", now=NOW)


def test_the_route_guard_fails_closed_in_production_and_accepts_only_a_valid_signature(monkeypatch):
    import time

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from routes.webhooks import require_resend_signature

    app = FastAPI()

    @app.post("/hook", dependencies=[Depends(require_resend_signature)])
    async def hook():
        return {"ok": True}

    client = TestClient(app)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    assert client.post("/hook", content=BODY).status_code == 403  # no secret in production: refused
    secret = _secret()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)
    now = int(time.time())
    assert client.post("/hook", content=BODY).status_code == 403  # unsigned
    assert client.post("/hook", content=BODY, headers=_signed(BODY, _secret(), stamp=now)).status_code == 403
    assert client.post("/hook", content=BODY, headers=_signed(BODY, secret, stamp=now)).status_code == 200
