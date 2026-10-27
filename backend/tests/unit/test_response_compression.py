"""Big answers are compressed on the wire; small ones and clients that did not ask stay plain. CORS stays outermost."""

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)
ORIGIN = "http://localhost:3000"


def test_a_big_answer_is_gzipped_when_the_client_accepts_it():
    resp = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "gzip"
    assert resp.json()["openapi"]  # the client library inflates it transparently


def test_a_client_that_does_not_accept_gzip_gets_the_plain_body():
    resp = client.get("/openapi.json", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in resp.headers and resp.json()["openapi"]


def test_a_tiny_answer_is_left_alone():
    resp = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200 and "content-encoding" not in resp.headers


def test_the_cors_headers_are_on_a_compressed_answer_too():
    resp = client.get("/openapi.json", headers={"Accept-Encoding": "gzip", "Origin": ORIGIN})
    assert resp.headers["content-encoding"] == "gzip"
    assert resp.headers["access-control-allow-origin"] == ORIGIN
