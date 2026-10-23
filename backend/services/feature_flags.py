"""Feature flags for dangerous capabilities. Every flag is OFF unless explicitly enabled in the environment.

    FEATURE_LIVE_SENDING=true      allow real e-mail dispatch (SMTP, see services/smtp_svc.py)
    FEATURE_EXTERNAL_SOURCES=true  allow fetching each prospect's own public homepage (robots.txt, see site_fetcher_svc)
    FEATURE_PROSPECT_IMPORT=true   allow importing a prospect list (CSV/JSON) with its origin and legal basis
    FEATURE_DEMO_DATA=true         offer the built-in demo directory as a source (off: only real sources are listed)

`dry_run()` is the inverse of live sending: with no flag set, nothing leaves the system.
`SEND_KILL_SWITCH=true` (see `kill_switch()`) halts every send regardless of the flags above.
While live sending is on, `OUTREACH_SANDBOX` (on unless set to false) restricts recipients to `OUTREACH_LIVE_ALLOWLIST`
(e-mail addresses or domains) and `OUTREACH_LIVE_PHONES` (WhatsApp numbers).
`OUTREACH_TEST_SINK=true` swaps the providers for an in-process recorder for automated tests only: it is ignored when
`APP_ENV=production`, so a real deployment can never record a send that did not happen.
"""

from __future__ import annotations

import os

from services.outreach_os import sandbox as sandbox_rules
from services.outreach_os.normalize import normalize_phone

KNOWN_FLAGS = ("live_sending", "external_sources", "prospect_import", "demo_data")


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


def live_phones() -> tuple[str, ...]:
    """WhatsApp numbers (E.164) allowed a real message while the sandbox is on; unreadable entries are dropped."""
    found: list[str] = []
    for entry in sandbox_rules.parse_allowlist(os.environ.get("OUTREACH_LIVE_PHONES")):
        number = normalize_phone(entry)
        if number and number not in found:
            found.append(number)
    return tuple(found)


def test_sink() -> bool:
    """Automated tests only: record sends in-process instead of calling a provider. Never in production."""
    if os.environ.get("APP_ENV", "").strip().lower() == "production":
        return False
    return os.environ.get("OUTREACH_TEST_SINK", "").strip().lower() in {"1", "true", "yes", "on"}


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
