"""The free Overpass relay (a Netlify function) must ask the same public servers as the API, and be reachable at the
path the browser and OVERPASS_RELAY_URL use. Pure file checks: no network."""

import re
from pathlib import Path

from services import overpass_svc

ROOT = Path(__file__).resolve().parents[3]
RELAY = ROOT / "frontend" / "src" / "lib" / "overpassRelay.js"
FUNCTION = ROOT / "frontend" / "netlify" / "functions" / "overpass.mjs"
BROWSER = ROOT / "frontend" / "src" / "lib" / "overpassBrowser.js"


def _mirrors() -> list[str]:
    block = re.search(r"RELAY_MIRRORS = \[(.*?)\];", RELAY.read_text(), re.S)
    assert block, "RELAY_MIRRORS not found"
    return re.findall(r'"(https://[^"]+)"', block.group(1))


def test_the_relay_asks_the_same_public_servers_as_the_api():
    assert _mirrors() == list(overpass_svc.ENDPOINTS)


def test_the_function_is_routed_at_the_path_the_browser_asks():
    toml = (ROOT / "netlify.toml").read_text()
    assert 'directory = "netlify/functions"' in toml
    redirect = re.search(
        r'from = "/relay/overpass"\s+to = "/.netlify/functions/overpass"\s+status = 200\s+force = true', toml
    )
    assert redirect, "the relay path must be rewritten to the function, before the SPA fallback"
    assert toml.index("/relay/overpass") < toml.index('from = "/*"')  # the SPA fallback would otherwise swallow it
    assert 'RELAY_PATH = "/relay/overpass"' in BROWSER.read_text()
    assert "export default async" in FUNCTION.read_text()


def test_the_function_never_forwards_to_a_server_a_client_names():
    text = FUNCTION.read_text()
    assert "RELAY_MIRRORS" in text and "acceptableQuery" in text and "originAllowed" in text
    assert "searchParams" not in text and 'get("url")' not in text  # no client-chosen target: not an open proxy
