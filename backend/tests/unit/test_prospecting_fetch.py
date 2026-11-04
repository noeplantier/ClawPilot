"""The Celery discovery task reads Overpass through the shared client: a silent server no longer holds it for minutes.

Before (measured with a server that never answers): 73 s for one such server, about 2 min 25 s for two, because the task
had its own endpoint list, 35 s per request, two attempts per server and no memory of a server that had just failed."""

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from services import overpass_svc
from tasks import prospecting_tasks

ELEMENTS = [{"type": "node", "id": 1, "lat": 48.1, "lon": -2.7, "tags": {"name": "Chez Test", "amenity": "restaurant"}}]


class _Server:
    def __init__(self, delay: float):
        outer = self
        self.calls = 0

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.calls += 1
                time.sleep(delay)
                try:
                    body = json.dumps({"elements": ELEMENTS}).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:  # the client gave up on the silent server
                    pass

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/interpreter"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def servers(monkeypatch):
    made = []

    def make(*delays):
        made.extend(_Server(d) for d in delays)
        monkeypatch.setenv("OVERPASS_ENDPOINTS", ",".join(s.url for s in made))
        overpass_svc.reset_cooldown()
        return made

    yield make
    for s in made:
        s.close()
    overpass_svc.reset_cooldown()


def test_a_silent_server_costs_one_short_timeout_then_the_next_answers(servers, monkeypatch):
    monkeypatch.setattr(overpass_svc, "TIMEOUT_SECONDS", 0.4)
    silent, ok = servers(3.0, 0.0)
    started = time.monotonic()
    elements = asyncio.run(prospecting_tasks._fetch_overpass([48.0, -2.8, 48.2, -2.6], "restaurant"))
    assert elements == ELEMENTS
    assert time.monotonic() - started < 2.0  # not 73 s: one timeout of the shared client, then the healthy server
    assert silent.calls == 1 and ok.calls == 1  # no second attempt on the server that did not answer


def test_the_next_search_does_not_wait_on_the_server_that_just_failed(servers, monkeypatch):
    monkeypatch.setattr(overpass_svc, "TIMEOUT_SECONDS", 0.4)
    silent, ok = servers(3.0, 0.0)
    asyncio.run(prospecting_tasks._fetch_overpass([48.0, -2.8, 48.2, -2.6], "restaurant"))
    started = time.monotonic()
    asyncio.run(prospecting_tasks._fetch_overpass([48.0, -2.8, 48.2, -2.6], "restaurant"))
    assert time.monotonic() - started < 0.3  # the failing server is tried last now
    assert silent.calls == 1 and ok.calls == 2


def test_every_server_down_is_one_explained_failure_not_a_hang(servers, monkeypatch):
    monkeypatch.setattr(overpass_svc, "TIMEOUT_SECONDS", 0.3)
    servers(2.0, 2.0)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="overpass_unavailable"):
        asyncio.run(prospecting_tasks._fetch_overpass([48.0, -2.8, 48.2, -2.6], "restaurant"))
    assert time.monotonic() - started < 2.0
