"""Twilio webhook signature verification — pure logic plus the route guard, fully offline."""

import secrets

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from routes.webhooks import require_twilio_signature
from services import twilio_svc

TOKEN = secrets.token_hex(16)  # random per run: no credential literal in the repo
URL = "http://testserver/hook"
PARAMS = {"Body": "STOP", "From": "whatsapp:+14155550101", "MessageSid": "SM123"}


def _sign(params=PARAMS, url=URL, token=TOKEN):
    return RequestValidator(token).compute_signature(url, params)


# ---- verify_signature ----------------------------------------------------------------------
def test_valid_signature_accepted():
    assert twilio_svc.verify_signature(URL, PARAMS, _sign(), token=TOKEN)


@pytest.mark.parametrize("signature", [None, "", "not-a-signature"])
def test_missing_or_bad_signature_rejected(signature):
    assert not twilio_svc.verify_signature(URL, PARAMS, signature, token=TOKEN)


def test_signature_from_other_token_rejected():
    assert not twilio_svc.verify_signature(URL, PARAMS, _sign(token=secrets.token_hex(16)), token=TOKEN)


def test_tampered_params_or_url_rejected():
    sig = _sign()
    assert not twilio_svc.verify_signature(URL, {**PARAMS, "Body": "YES"}, sig, token=TOKEN)
    assert not twilio_svc.verify_signature("http://testserver/other", PARAMS, sig, token=TOKEN)


def test_no_token_never_verifies():
    assert not twilio_svc.verify_signature(URL, PARAMS, _sign(), token="")


# ---- route guard ---------------------------------------------------------------------------
@pytest.fixture
def client():
    app = FastAPI()

    @app.post("/hook", dependencies=[Depends(require_twilio_signature)])
    async def hook():
        return {"ok": True}

    return TestClient(app)


def _post(client, headers=None, data=PARAMS):
    return client.post("/hook", data=data, headers=headers or {})


def test_guard_with_token_rejects_unsigned_and_forged(client, monkeypatch):
    monkeypatch.setattr(twilio_svc, "TOKEN", TOKEN)
    monkeypatch.delenv("TWILIO_WEBHOOK_URL", raising=False)
    assert _post(client).status_code == 403
    assert _post(client, {"X-Twilio-Signature": "forged"}).status_code == 403
    assert _post(client, {"X-Twilio-Signature": _sign(token=secrets.token_hex(16))}).status_code == 403


def test_guard_with_token_accepts_valid_signature(client, monkeypatch):
    monkeypatch.setattr(twilio_svc, "TOKEN", TOKEN)
    monkeypatch.delenv("TWILIO_WEBHOOK_URL", raising=False)
    assert _post(client, {"X-Twilio-Signature": _sign()}).status_code == 200


def test_guard_honours_public_url_override(client, monkeypatch):
    """Behind a proxy the app-visible URL differs from the signed one."""
    public = "https://app.example.com/api/webhooks/twilio"
    monkeypatch.setattr(twilio_svc, "TOKEN", TOKEN)
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", public)
    assert _post(client, {"X-Twilio-Signature": _sign(url=public)}).status_code == 200
    assert _post(client, {"X-Twilio-Signature": _sign()}).status_code == 403  # signed for the internal URL


def test_guard_without_token_fails_closed_in_production(client, monkeypatch):
    monkeypatch.setattr(twilio_svc, "TOKEN", None)
    monkeypatch.setenv("APP_ENV", "production")
    assert _post(client).status_code == 403
    assert _post(client, {"X-Twilio-Signature": _sign()}).status_code == 403


def test_guard_without_token_allows_local_mock_mode(client, monkeypatch):
    monkeypatch.setattr(twilio_svc, "TOKEN", None)
    monkeypatch.setenv("APP_ENV", "development")
    assert _post(client).status_code == 200
