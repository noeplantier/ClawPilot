"""SendGrid event-webhook signature verification — offline, keys generated per run."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from routes.webhooks import require_sendgrid_signature
from services import sendgrid_svc

SIG_HEADER = "X-Twilio-Email-Event-Webhook-Signature"
TS_HEADER = "X-Twilio-Email-Event-Webhook-Timestamp"
TIMESTAMP = "1700000000"
BODY = json.dumps([{"event": "unsubscribe", "sg_message_id": "abc.filter0001"}]).encode()


def _keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    public_b64 = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    ).decode()
    return private, public_b64


def _sign(private, body=BODY, timestamp=TIMESTAMP):
    return base64.b64encode(private.sign(timestamp.encode() + body, ec.ECDSA(hashes.SHA256()))).decode()


@pytest.fixture(scope="module")
def keys():
    return _keypair(), _keypair()  # (trusted, attacker)


# ---- verify_event_signature ----------------------------------------------------------------
def test_valid_signature_accepted(keys):
    (private, public), _ = keys
    assert sendgrid_svc.verify_event_signature(BODY, _sign(private), TIMESTAMP, public_key=public)


def test_wrong_key_tampered_body_or_timestamp_rejected(keys):
    (private, public), (attacker, _) = keys
    assert not sendgrid_svc.verify_event_signature(BODY, _sign(attacker), TIMESTAMP, public_key=public)
    assert not sendgrid_svc.verify_event_signature(BODY + b" ", _sign(private), TIMESTAMP, public_key=public)
    assert not sendgrid_svc.verify_event_signature(BODY, _sign(private), "1700000001", public_key=public)


@pytest.mark.parametrize("signature,timestamp", [(None, TIMESTAMP), ("", TIMESTAMP), ("x", None), ("%%%", TIMESTAMP)])
def test_missing_or_malformed_headers_rejected_without_raising(keys, signature, timestamp):
    (_, public), _ = keys
    assert not sendgrid_svc.verify_event_signature(BODY, signature, timestamp, public_key=public)


def test_missing_or_garbage_key_rejected(keys):
    (private, _), _ = keys
    assert not sendgrid_svc.verify_event_signature(BODY, _sign(private), TIMESTAMP, public_key="")
    assert not sendgrid_svc.verify_event_signature(BODY, _sign(private), TIMESTAMP, public_key="not-a-key")


# ---- route guard ---------------------------------------------------------------------------
@pytest.fixture
def client():
    app = FastAPI()

    @app.post("/hook", dependencies=[Depends(require_sendgrid_signature)])
    async def hook():
        return {"ok": True}

    return TestClient(app)


def _post(client, headers=None):
    return client.post("/hook", content=BODY, headers=headers or {})


def test_guard_with_key_rejects_unsigned_and_forged(client, keys, monkeypatch):
    (_, public), (attacker, _) = keys
    monkeypatch.setattr(sendgrid_svc, "WEBHOOK_PUBLIC_KEY", public)
    assert _post(client).status_code == 403
    assert _post(client, {SIG_HEADER: _sign(attacker), TS_HEADER: TIMESTAMP}).status_code == 403


def test_guard_with_key_accepts_valid_signature(client, keys, monkeypatch):
    (private, public), _ = keys
    monkeypatch.setattr(sendgrid_svc, "WEBHOOK_PUBLIC_KEY", public)
    assert _post(client, {SIG_HEADER: _sign(private), TS_HEADER: TIMESTAMP}).status_code == 200


def test_guard_without_key_fails_closed_in_production(client, monkeypatch):
    monkeypatch.setattr(sendgrid_svc, "WEBHOOK_PUBLIC_KEY", None)
    monkeypatch.setenv("APP_ENV", "production")
    assert _post(client).status_code == 403


def test_guard_without_key_allows_local_mock_mode(client, monkeypatch):
    monkeypatch.setattr(sendgrid_svc, "WEBHOOK_PUBLIC_KEY", None)
    monkeypatch.setenv("APP_ENV", "development")
    assert _post(client).status_code == 200
