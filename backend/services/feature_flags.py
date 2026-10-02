"""Feature flags for dangerous capabilities. Every flag is OFF unless explicitly enabled in the environment.

    FEATURE_LIVE_SENDING=true      allow real e-mail dispatch (SMTP, see services/smtp_svc.py)
    FEATURE_EXTERNAL_SOURCES=true  allow network-backed discovery sources (not implemented yet)

`dry_run()` is the inverse of live sending: with no flag set, nothing leaves the system.
`SEND_KILL_SWITCH=true` (see `kill_switch()`) halts every send regardless of the flags above.
While live sending is on, `OUTREACH_SANDBOX` (on unless set to false) restricts recipients to `OUTREACH_LIVE_ALLOWLIST`.
"""

from __future__ import annotations

import os

from services.outreach_os import sandbox as sandbox_rules

KNOWN_FLAGS = ("live_sending", "external_sources")


def is_enabled(name: str) -> bool:
    if name not in KNOWN_FLAGS:
        raise KeyError(f"unknown feature flag: {name}")
    return os.environ.get(f"FEATURE_{name.upper()}", "").strip().lower() in {"1", "true", "yes", "on"}


def dry_run() -> bool:
    return not is_enabled("live_sending")


def sandbox() -> bool:
    """On unless `OUTREACH_SANDBOX` is explicitly set to a false value: going live is a deliberate second step."""
    return os.environ.get("OUTREACH_SANDBOX", "").strip().lower() not in {"0", "false", "no", "off"}


def live_allowlist() -> tuple[str, ...]:
    return sandbox_rules.parse_allowlist(os.environ.get("OUTREACH_LIVE_ALLOWLIST"))


def snapshot() -> dict[str, bool]:
    return {name: is_enabled(name) for name in KNOWN_FLAGS} | {
        "dry_run": dry_run(),
        "kill_switch": kill_switch(),
        "sandbox": sandbox(),
    }


def kill_switch() -> bool:
    """Emergency stop (`SEND_KILL_SWITCH=true`): refuses every outbound send — dry-run dispatch, SendGrid and Twilio.

    Deliberately an environment variable, not a database row: it must work when the database is slow, or
    when someone with only deploy access has to halt sending immediately.
    """
    return os.environ.get("SEND_KILL_SWITCH", "").strip().lower() in {"1", "true", "yes", "on"}
