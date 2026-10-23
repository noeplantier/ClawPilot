"""The real http_fetch against a FAKE Overpass on 127.0.0.1: the HTTP code path, with no outside network.
Each scenario scripts what the fake server does on its successive calls."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from services import overpass_svc

FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "osm" / "overpass_lyon.json").read_text())


class _Fake:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.calls.append((self.path, self.rfile.read(length).decode(), self.headers.get("User-Agent")))
                step = outer.script.pop(0) if outer.script else ("status", 500)
                kind = step[0]
                if kind == "slow":
                    time.sleep(step[1])
                if kind == "status":
                    self.send_response(step[1])
                    self.end_headers()
                    return
                body = step[1] if kind in ("json", "raw") else b""
                payload = json.dumps(body).encode() if kind == "json" else body
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/interpreter"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake(monkeypatch):
    made = []

    def make(*script, servers=1):
        servers_ = [_Fake(script if i == 0 else []) for i in range(servers)]
        made.extend(servers_)
        monkeypatch.setenv("OVERPASS_ENDPOINTS", ",".join(s.url for s in servers_))
        return servers_

    yield make
    for f in made:
        f.close()


def test_a_real_request_reaches_the_server_identified_and_returns_the_elements(fake):
    (server,) = fake(("json", FIXTURE))
    assert overpass_svc.http_fetch("[out:json];node(1);out;")["elements"] == FIXTURE["elements"]
    path, body, agent = server.calls[0]
    assert path == "/api/interpreter" and body.startswith("data=") and agent  # an identified User-Agent, never empty


def test_a_429_makes_the_client_try_the_next_server_in_turn_not_in_parallel(fake):
    first, second = fake(("status", 429), servers=2)
    second.script = [("json", FIXTURE)]
    assert len(overpass_svc.http_fetch("q")["elements"]) == len(FIXTURE["elements"])
    assert len(first.calls) == 1 and len(second.calls) == 1


def test_every_server_busy_is_one_explained_failure(fake):
    fake(("status", 429), servers=2)
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("q")
    assert err.value.code == "overpass_busy" and len(err.value.failures) == 2


def test_a_slow_server_times_out_and_the_next_one_answers(fake, monkeypatch):
    monkeypatch.setattr(overpass_svc, "TIMEOUT_SECONDS", 0.3)
    slow, ok = fake(("slow", 1.0), servers=2)
    ok.script = [("json", FIXTURE)]
    assert overpass_svc.http_fetch("q")["elements"]
    assert len(slow.calls) == 1 and len(ok.calls) == 1


def test_a_client_error_is_not_retried_elsewhere(fake):
    first, second = fake(("status", 400), servers=2)
    with pytest.raises(overpass_svc.Unavailable):
        overpass_svc.http_fetch("bad")
    assert len(second.calls) == 0


@pytest.mark.parametrize(
    "step,code",
    [
        (("raw", b"<html>Gateway</html>"), "overpass_bad_answer"),
        (("json", {"hello": 1}), "overpass_bad_answer"),
        (("json", {"elements": [], "remark": "runtime error: Query timed out"}), "overpass_busy"),
    ],
)
def test_garbage_and_server_side_timeouts_are_failures_not_empty_results(fake, step, code):
    fake(step)
    with pytest.raises(overpass_svc.Unavailable) as err:
        overpass_svc.http_fetch("q")
    assert err.value.code == code


def test_the_probe_reads_the_status_page_of_a_fake_server(fake, monkeypatch):
    (server,) = fake()
    server.server.RequestHandlerClass.do_GET = lambda self: (
        self.send_response(200),
        self.end_headers(),
        self.wfile.write(b"ok"),
    )
    result = overpass_svc.probe(server.url)
    assert result["ok"] is True and result["status"] == 200 and result["host"] == "127.0.0.1"
