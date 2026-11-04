"""Overpass client: no socket is opened, urlopen is replaced."""

import io
import json
import urllib.error

import pytest

from services import overpass_svc
from services.outreach_os import map_jobs


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
    # runs in the background: the total only has to stay under the time after which a job counts as lost
    assert len(overpass_svc.ENDPOINTS) * overpass_svc.TIMEOUT_SECONDS < map_jobs.JOB_STALE_SECONDS
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


def _answering(body):
    return lambda request, timeout: _Answer(json.dumps(body).encode())


def test_an_answer_without_elements_is_not_an_answer(monkeypatch):
    monkeypatch.setattr(overpass_svc, "_open", _answering({"hello": "world"}))
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("[out:json];")
    assert err.value.code == "overpass_bad_answer" and len(err.value.failures) == len(overpass_svc.ENDPOINTS)


def test_a_runtime_error_remark_is_busy_even_with_http_200(monkeypatch):
    body = {"elements": [], "remark": 'runtime error: Query timed out in "query" at line 3 after 26 seconds.'}
    monkeypatch.setattr(overpass_svc, "_open", _answering(body))
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("[out:json];")
    assert err.value.code == "overpass_busy"


def test_the_error_code_follows_what_the_servers_did(monkeypatch):
    def fake(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "slow down", {}, None)

    monkeypatch.setattr(overpass_svc, "_open", fake)
    with pytest.raises(overpass_svc.Unavailable) as busy:
        overpass_svc.http_fetch("q")
    assert busy.value.code == "overpass_busy"
    monkeypatch.setattr(overpass_svc, "_open", lambda r, t: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(overpass_svc.Unavailable) as slow:
        overpass_svc.http_fetch("q")
    assert slow.value.code == "overpass_timeout"
    monkeypatch.setattr(
        overpass_svc, "_open", lambda r, t: (_ for _ in ()).throw(urllib.error.URLError(OSError(101, "x")))
    )
    with pytest.raises(overpass_svc.Unavailable) as down:
        overpass_svc.http_fetch("q")
    assert down.value.code == "overpass_unreachable"


def test_probe_reports_facts_without_raising(monkeypatch):
    monkeypatch.setattr(overpass_svc, "_open", lambda r, t: (_ for _ in ()).throw(TimeoutError()))
    down = overpass_svc.probe("https://overpass.example/api/interpreter")
    assert down["ok"] is False and down["host"] == "overpass.example" and "TimeoutError" in down["error"]

    class _Status(_Answer):
        status = 200

    monkeypatch.setattr(overpass_svc, "_open", lambda r, t: _Status(b"Connected as: 1"))
    assert overpass_svc.probe("https://overpass.example/api/interpreter")["ok"] is True


def test_a_server_that_just_failed_is_tried_last_then_first_again_after_the_cooldown(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(overpass_svc, "_clock", lambda: clock["now"])
    monkeypatch.setenv("OVERPASS_ENDPOINTS", "https://a.example/i,https://b.example/i,https://c.example/i")
    order = []

    def fake(request, timeout):
        order.append(request.full_url)
        if "a.example" in request.full_url:
            raise TimeoutError()
        return _Answer(json.dumps({"elements": []}).encode())

    monkeypatch.setattr(overpass_svc, "_open", fake)
    overpass_svc.http_fetch("q")
    assert order == ["https://a.example/i", "https://b.example/i"] and overpass_svc.cooling_hosts() == ["a.example"]
    order.clear()
    overpass_svc.http_fetch("q")
    assert order == ["https://b.example/i"]  # the cooling server is not waited on again
    clock["now"] += overpass_svc.COOLDOWN_SECONDS + 1
    order.clear()
    overpass_svc.http_fetch("q")
    assert order[0] == "https://a.example/i" and overpass_svc.cooling_hosts() == [
        "a.example"
    ]  # tried again, fails again


def test_when_every_server_is_cooling_all_of_them_are_still_tried(monkeypatch):
    monkeypatch.setenv("OVERPASS_ENDPOINTS", "https://a.example/i,https://b.example/i")
    monkeypatch.setattr(overpass_svc, "_open", lambda r, t: (_ for _ in ()).throw(TimeoutError()))
    for _ in range(2):
        with pytest.raises(overpass_svc.Unavailable) as err:
            overpass_svc.http_fetch("q")
        assert len(err.value.failures) == 2
    monkeypatch.setattr(overpass_svc, "_open", _answering({"elements": []}))
    assert overpass_svc.http_fetch("q") == {"elements": []}  # a recovered server answers even while "cooling"
    assert overpass_svc.cooling_hosts() == ["b.example"]  # only the one that answered is cleared


def test_a_success_clears_the_cooldown_and_a_client_error_never_starts_one(monkeypatch):
    monkeypatch.setenv("OVERPASS_ENDPOINTS", "https://a.example/i")
    monkeypatch.setattr(
        overpass_svc,
        "_open",
        lambda r, t: (_ for _ in ()).throw(urllib.error.HTTPError(r.full_url, 400, "bad", {}, None)),
    )
    with pytest.raises(overpass_svc.Unavailable):
        overpass_svc.http_fetch("q")
    assert overpass_svc.cooling_hosts() == []
    monkeypatch.setattr(overpass_svc, "_open", lambda r, t: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(overpass_svc.Unavailable):
        overpass_svc.http_fetch("q")
    assert overpass_svc.cooling_hosts() == ["a.example"]
    monkeypatch.setattr(overpass_svc, "_open", _answering({"elements": []}))
    overpass_svc.http_fetch("q")
    assert overpass_svc.cooling_hosts() == []


def test_a_server_that_refuses_us_with_403_is_skipped_not_a_reason_to_stop(monkeypatch):
    """Production, measured: overpass-api.de refused the connection and overpass.openstreetmap.fr answered 403, and the
    search gave up there without ever asking the three other public servers."""
    seen = []

    def fake(request, timeout):
        seen.append(request.full_url)
        if "openstreetmap.fr" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        if "overpass-api.de" in request.full_url:
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        return _Answer(json.dumps({"elements": [{"id": 1}]}).encode())

    monkeypatch.setattr(overpass_svc, "_open", fake)
    assert overpass_svc.http_fetch("[out:json];") == {"elements": [{"id": 1}]}
    assert seen[:3] == list(overpass_svc.ENDPOINTS[:3])  # .de refused, .fr 403, then private.coffee answered
    assert sorted(overpass_svc.cooling_hosts()) == ["overpass-api.de", "overpass.openstreetmap.fr"]


def test_when_every_server_refuses_each_one_is_named_and_none_is_skipped(monkeypatch):
    def fake(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(overpass_svc, "_open", fake)
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("q")
    assert len(err.value.failures) == len(overpass_svc.ENDPOINTS) and err.value.code == "overpass_unreachable"


def test_a_slow_server_is_hedged_by_the_next_one_and_nobody_waits_for_the_loser(monkeypatch):
    import threading
    import time

    monkeypatch.setattr(overpass_svc, "HEDGE_SECONDS", 0.05)
    release = threading.Event()
    seen = []

    def fake(request, timeout):
        seen.append(request.full_url)
        if "overpass-api.de" in request.full_url:
            release.wait(5)  # silent: it would answer only after a long time
            raise TimeoutError()
        return _Answer(json.dumps({"elements": []}).encode())

    monkeypatch.setattr(overpass_svc, "_open", fake)
    started = time.monotonic()
    try:
        assert overpass_svc.http_fetch("q") == {"elements": []}
        assert time.monotonic() - started < 2  # the silent first server did not hold the search back
    finally:
        release.set()
    assert [u for u in seen] == list(overpass_svc.ENDPOINTS[:2])  # asked in order, the hedge being the second one


def test_never_more_than_max_parallel_requests_are_in_flight(monkeypatch):
    import threading
    import time

    monkeypatch.setattr(overpass_svc, "HEDGE_SECONDS", 0.02)
    lock = threading.Lock()
    state = {"now": 0, "max": 0}

    def fake(request, timeout):
        if "mail.ru" in request.full_url:  # the last of the five: the four before it are all slow
            return _Answer(json.dumps({"elements": []}).encode())
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        try:
            time.sleep(0.2)
            raise TimeoutError()
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr(overpass_svc, "_open", fake)
    assert overpass_svc.http_fetch("q") == {"elements": []}
    assert 1 < state["max"] <= 2  # hedged (more than one at a time), never more than two for one search


def test_a_relay_comes_first_only_when_it_is_an_https_url_and_an_explicit_list_wins(monkeypatch):
    monkeypatch.delenv("OVERPASS_ENDPOINTS", raising=False)
    monkeypatch.setenv("OVERPASS_RELAY_URL", "https://plantiers.example/relay/overpass")
    assert overpass_svc.endpoints() == ("https://plantiers.example/relay/overpass",) + overpass_svc.ENDPOINTS
    for bad in ("http://insecure.example/x", "javascript:alert(1)", "not a url", ""):
        monkeypatch.setenv("OVERPASS_RELAY_URL", bad)
        assert overpass_svc.endpoints() == overpass_svc.ENDPOINTS, bad
    monkeypatch.setenv("OVERPASS_RELAY_URL", "https://plantiers.example/relay/overpass")
    monkeypatch.setenv("OVERPASS_ENDPOINTS", "https://mine.example/i")
    assert overpass_svc.endpoints() == ("https://mine.example/i",)  # a self-hosted list replaces everything
