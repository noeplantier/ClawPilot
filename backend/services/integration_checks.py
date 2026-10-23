"""Live checks behind the "Test" buttons of Settings > Integrations. Each one answers with facts, never a secret.

Every check is read-only and sends nothing to a person: it connects, signs in or reads one public status page.
The seams (probe, fetchers, client factories) are parameters so tests replay them offline; the route passes the real
ones.
Result: {"ok", "outcome": passed|failed|skipped, "latency_ms", "detail"} — `skipped` means nothing was attempted
(missing configuration, flag off), which is different from a failure.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from services import feature_flags, imap_svc, overpass_svc, registry_svc, sendgrid_svc, smtp_svc, twilio_svc


def _result(outcome: str, detail: str, started: Optional[float] = None) -> dict[str, Any]:
    latency = int((time.monotonic() - started) * 1000) if started is not None else None
    return {"ok": outcome == "passed", "outcome": outcome, "latency_ms": latency, "detail": detail}


def _status_of(exc: Exception) -> Optional[int]:
    for name in ("status_code", "status", "code"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    return None


def database(latency_ms: Optional[int], error: Optional[str]) -> dict[str, Any]:
    """The route runs the query (it owns the session); this only shapes the answer."""
    if error:
        return {"ok": False, "outcome": "failed", "latency_ms": None, "detail": error}
    return {"ok": True, "outcome": "passed", "latency_ms": latency_ms, "detail": "A query ran against the database."}


def osm(probe: Callable[[str], dict[str, Any]] = overpass_svc.probe) -> dict[str, Any]:
    started = time.monotonic()
    answers = [probe(endpoint) for endpoint in overpass_svc.endpoints()]  # one after the other: never a burst
    up = [a for a in answers if a.get("ok")]
    detail = ", ".join(
        f"{a.get('host')}: "
        + (f"{a.get('ms')} ms" if a.get("ok") else str(a.get("error") or f"HTTP {a.get('status')}"))
        for a in answers
    )
    if not up:
        return _result(
            "failed",
            f"No OpenStreetMap server answered from this host ({detail}). The map falls back to your browser.",
            started,
        )
    return _result("passed", f"{len(up)} of {len(answers)} servers answered ({detail}).", started)


def registry(fetch: Callable[[dict[str, Any]], dict[str, Any]] = registry_svc.fetch_page) -> dict[str, Any]:
    if not feature_flags.is_enabled("external_sources"):
        return _result("skipped", "FEATURE_EXTERNAL_SOURCES is off: network sources are not queried.")
    started = time.monotonic()
    try:
        data = fetch({"q": "boulangerie", "per_page": 1, "page": 1})
    except registry_svc.Unavailable as exc:
        return _result("failed", str(exc), started)
    total = data.get("total_results")
    return _result(
        "passed",
        "The registry answered" + (f" ({total} matches for a sample query)." if isinstance(total, int) else "."),
        started,
    )


def smtp(check: Callable[[], dict[str, Any]] = smtp_svc.check_connection) -> dict[str, Any]:
    if not smtp_svc.is_configured():
        return _result("skipped", "SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD are not all set.")
    started = time.monotonic()
    answer = check()
    if answer.get("ok"):
        return _result("passed", "Connected over TLS and signed in. Nothing was sent.", started)
    return _result("failed", f"{answer.get('error')} (step: {answer.get('phase')}).", started)


def imap(check: Callable[[], dict[str, Any]] = imap_svc.check_connection) -> dict[str, Any]:
    if not imap_svc.is_configured():
        return _result("skipped", "IMAP_HOST, IMAP_USERNAME and IMAP_PASSWORD are not all set.")
    started = time.monotonic()
    answer = check()
    if answer.get("ok"):
        return _result("passed", "Signed in over TLS and opened the folder read-only. No message was touched.", started)
    return _result("failed", f"{answer.get('error')} (step: {answer.get('phase')}).", started)


def _sendgrid_client(key: str) -> Any:
    from sendgrid import SendGridAPIClient

    return SendGridAPIClient(key)


def _twilio_client(sid: str, token: str) -> Any:
    from twilio.rest import Client

    return Client(sid, token)


def sendgrid(client: Optional[Callable[[str], Any]] = None) -> dict[str, Any]:
    """Reads the key's scopes: proves the key is valid without sending anything."""
    if not sendgrid_svc.is_configured():
        return _result("skipped", "SENDGRID_API_KEY and SENDGRID_FROM_EMAIL are not both set.")
    started = time.monotonic()
    try:
        response = (client or _sendgrid_client)(sendgrid_svc.API_KEY or "").client.scopes.get()
        code = int(response.status_code)
    except Exception as exc:  # noqa: BLE001 (the error text may echo request details: only class and code)
        code = _status_of(exc) or 0
        if code in (401, 403):
            return _result("failed", f"SendGrid rejected the key (HTTP {code}).", started)
        return _result(
            "failed",
            f"SendGrid could not be reached ({type(exc).__name__}{f', HTTP {code}' if code else ''}).",
            started,
        )
    if 200 <= code < 300:
        return _result("passed", "SendGrid accepted the key.", started)
    return _result("failed", f"SendGrid answered HTTP {code}.", started)


def twilio(client: Optional[Callable[[str, str], Any]] = None) -> dict[str, Any]:
    """Reads the account record: proves the SID and token match without sending anything."""
    if not twilio_svc.is_configured():
        return _result("skipped", "TWILIO_ACCOUNT_SID (starting with AC) and TWILIO_AUTH_TOKEN are not both set.")
    started = time.monotonic()
    try:
        sid = twilio_svc.SID or ""
        account = (client or _twilio_client)(sid, twilio_svc.TOKEN or "").api.accounts(sid).fetch()
        state = str(getattr(account, "status", "") or "")
    except Exception as exc:  # noqa: BLE001
        code = _status_of(exc) or 0
        if code in (401, 403):
            return _result("failed", f"Twilio rejected the credentials (HTTP {code}).", started)
        return _result(
            "failed", f"Twilio could not be reached ({type(exc).__name__}{f', HTTP {code}' if code else ''}).", started
        )
    if state and state != "active":
        return _result("failed", f"The Twilio account is {state}.", started)
    return _result("passed", "Twilio accepted the credentials.", started)
