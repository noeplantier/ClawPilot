"""HTTP client for the French open company registry (recherche-entreprises.api.gouv.fr). Network I/O, flag-gated.

Keyless and free. Polite: identified User-Agent, 20 s timeout, 2 MB cap, one retry-free request per page (the caller
stops at the first short page). A 429/5xx is reported as `Unavailable`, never retried in a loop.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from services.site_fetcher_svc import PRODUCT, user_agent

URL = "https://recherche-entreprises.api.gouv.fr/search"
TIMEOUT_SECONDS = 20.0
MAX_BYTES = 2_000_000


class Unavailable(Exception):
    pass


def fetch_page(params: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": user_agent() or PRODUCT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (https, fixed host)
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise Unavailable("the registry answer is too large: narrow the area")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise Unavailable("unexpected registry answer")
        return data
    except urllib.error.HTTPError as exc:
        raise Unavailable(f"the company registry answered HTTP {exc.code}; try again in a minute")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise Unavailable(f"the company registry is unreachable ({type(exc).__name__})")
