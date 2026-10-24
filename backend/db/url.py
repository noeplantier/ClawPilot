"""Normalise DATABASE_URL to the asyncpg driver.

Managed hosts (Render, Supabase, Heroku…) hand out `postgres://` or `postgresql://`; SQLAlchemy's
async engine needs `postgresql+asyncpg://`. Already-qualified URLs pass through untouched.
asyncpg has no `sslmode` option (libpq's): `sslmode=require` and friends are translated to asyncpg's `ssl=`.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SSLMODE_TO_SSL = {"disable": "disable", "allow": "prefer", "prefer": "prefer", "require": "require"}


def _translate_sslmode(url: str) -> str:
    parts = urlsplit(url)
    if "sslmode" not in parts.query:
        return url
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            # verify-ca / verify-full need a CA bundle asyncpg cannot take from a URL: use the closest safe value
            query.append(("ssl", _SSLMODE_TO_SSL.get(value, "require")))
        else:
            query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def async_database_url() -> str:
    url = os.environ["DATABASE_URL"]
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
            break
    return _translate_sslmode(url)


def describe_database() -> dict[str, str]:
    """Where the app connects, without any secret: host kind and port only (for the health page)."""
    parts = urlsplit(os.environ.get("DATABASE_URL", ""))
    host = parts.hostname or ""
    if host.endswith(".pooler.supabase.com"):
        kind = "supabase_transaction_pooler" if parts.port == 6543 else "supabase_session_pooler"
    elif host.endswith(".supabase.co"):
        kind = "supabase_direct"  # IPv6 only on the free plan: hosts without IPv6 (Render) cannot reach it
    elif host.endswith(".render.com") or host.startswith("dpg-"):
        kind = "render_postgres"
    elif host in ("localhost", "127.0.0.1", "db"):
        kind = "local"
    else:
        kind = "other"
    return {"kind": kind, "port": str(parts.port or "")}
