"""Normalise DATABASE_URL to the asyncpg driver.

Managed hosts (Render, Heroku…) hand out `postgres://` or `postgresql://`; SQLAlchemy's
async engine needs `postgresql+asyncpg://`. Already-qualified URLs pass through untouched.
"""

from __future__ import annotations

import os


def async_database_url() -> str:
    url = os.environ["DATABASE_URL"]
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url
