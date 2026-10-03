"""Overpass client: no socket is opened, urlopen is replaced."""

import io
import json
import urllib.error

import pytest

from services import overpass_svc


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_every_public_server_is_tried_and_the_failures_are_named(monkeypatch):
    seen = []

    def fake(request, timeout):
        seen.append((request.full_url, timeout))
        raise TimeoutError()

    monkeypatch.setattr(overpass_svc, "_open", fake)
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("[out:json];")
    assert [u for u, _ in seen] == list(overpass_svc.ENDPOINTS)
    assert all(t == overpass_svc.TIMEOUT_SECONDS for _, t in seen)
    assert len(overpass_svc.ENDPOINTS) * overpass_svc.TIMEOUT_SECONDS <= 70  # fits under the host's request limit
    assert "overpass-api.de: TimeoutError" in str(err.value) and "private.coffee: TimeoutError" in str(err.value)


def test_a_later_server_answers_when_the_first_hangs(monkeypatch):
    def fake(request, timeout):
        if "overpass-api.de" in request.full_url:
            raise TimeoutError()
        return _Answer(json.dumps({"elements": []}).encode())

    monkeypatch.setattr(overpass_svc, "_open", fake)
    assert overpass_svc.http_fetch("[out:json];") == {"elements": []}


def test_a_client_error_is_not_retried_on_other_servers(monkeypatch):
    calls = []

    def fake(request, timeout):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, None)

    monkeypatch.setattr(overpass_svc, "_open", fake)
    with pytest.raises(overpass_svc.Unavailable):
        overpass_svc.http_fetch("bad query")
    assert len(calls) == 1


def test_the_cause_of_a_connection_error_is_kept_in_the_message(monkeypatch):
    def fake(request, timeout):
        raise urllib.error.URLError(OSError(101, "Network is unreachable"))

    monkeypatch.setattr(overpass_svc, "_open", fake)
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("[out:json];")
    assert "URLError (OSError: [Errno 101] Network is unreachable)" in str(err.value)


def test_connections_are_made_over_ipv4_only(monkeypatch):
    asked = []

    def fake_getaddrinfo(host, port, family, kind):
        asked.append(family)
        raise OSError("stop here")

    monkeypatch.setattr(overpass_svc.socket, "getaddrinfo", fake_getaddrinfo)
    conn = overpass_svc._IPv4Connection("overpass.example", 443, timeout=1)
    with pytest.raises(OSError):
        conn.connect()
    assert asked == [overpass_svc.socket.AF_INET]
