"""Feature flags for dangerous capabilities. Every flag is OFF unless explicitly enabled in the environment.

    FEATURE_LIVE_SENDING=true      allow real e-mail dispatch (not implemented yet)
    FEATURE_EXTERNAL_SOURCES=true  allow network-backed discovery sources (not implemented yet)

`dry_run()` is the inverse of live sending: with no flag set, nothing leaves the system.
"""

from __future__ import annotations

import os

KNOWN_FLAGS = ("live_sending", "external_sources")


def is_enabled(name: str) -> bool:
    if name not in KNOWN_FLAGS:
        raise KeyError(f"unknown feature flag: {name}")
    return os.environ.get(f"FEATURE_{name.upper()}", "").strip().lower() in {"1", "true", "yes", "on"}


def dry_run() -> bool:
    return not is_enabled("live_sending")


def snapshot() -> dict[str, bool]:
    return {name: is_enabled(name) for name in KNOWN_FLAGS} | {"dry_run": dry_run()}
