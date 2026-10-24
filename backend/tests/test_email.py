import pytest
from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app)

def test_allowlist_block():
    response = client.post("/email/send", json={"to": "unauthorized@example.com", "subject": "Test", "body": "Test"})
    assert response.status_code == 403

def test_allowlist_send():
    response = client.post("/email/send", json={"to": "founder@plantiers.com", "subject": "Test", "body": "Test"})
    assert response.status_code == 200