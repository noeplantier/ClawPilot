"""Live checks behind the "Test" buttons of Settings > Integrations. Each one answers with facts, never a secret.

Every check is read-only and sends nothing to a person: it connects, signs in or reads one public status page.
The seams (probe, fetchers, client factories) are parameters so tests replay them offline; the route passes the real
ones.
Result: {"ok", "outcome": passed|failed|skipped, "latency_ms", "detail"} — `skipped` means nothing was attempted
(missing configuration, flag off), which is different from a failure.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Optional

import requests

from services import (
    ai_svc,
    brevo_svc,
    feature_flags,
    imap_svc,
    overpass_svc,
    registry_svc,
    resend_svc,
    sendgrid_svc,
    smtp_svc,
    twilio_svc,
)
from services.outreach_os.normalize import normalize_email


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


RESEND_DOMAIN_STATES = frozenset(
    {"verified", "partially_verified", "pending", "not_started", "failed", "temporary_failure", "partially_failed"}
)


def _resend_error_name(response: Any) -> str:
    """Resend's error code only (e.g. "restricted_api_key"): never its message, which could repeat the request."""
    try:
        name = response.json().get("name")
    except Exception:  # noqa: BLE001 (no JSON body is an answer too)
        return ""
    return name if isinstance(name, str) and re.fullmatch(r"[a-z_]{1,40}", name) else ""


def _resend_domain_state(body: Any, domain: str) -> Optional[str]:
    """The state of the sender's domain in the account's list, "absent" when it is not there, None if unreadable.
    Only this domain is looked at: the other domains of the account are never returned."""
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("name", "")).strip().lower() == domain:
            state = str(row.get("status", ""))
            return state if state in RESEND_DOMAIN_STATES else "unknown"
    return "absent"


def resend(get: Callable[..., Any] = requests.get) -> dict[str, Any]:
    """Reads the account's domains (GET /domains): proves the key and says whether the sender's domain is verified,
    without sending anything. Nothing of the answer is echoed but that one domain's state. A sending-only key cannot
    read the domains: it is recognised, and the domain is left for the person to check in Resend."""
    config = resend_svc.ResendConfig.from_env()
    if config is None:
        return _result("skipped", "RESEND_API_KEY is not set.")
    sender = normalize_email(os.environ.get("OUTREACH_SENDER_EMAIL", "")) or ""
    domain = sender.rsplit("@", 1)[1] if "@" in sender else ""
    started = time.monotonic()
    try:
        response = get(
            f"{resend_svc.API_ROOT}/domains",
            headers={"Authorization": f"Bearer {config.api_key}", "Accept": "application/json"},
            timeout=(5, 15),
            allow_redirects=False,
        )
    except requests.Timeout:
        return _result("failed", "Resend did not answer in time.", started)
    except requests.RequestException as exc:
        return _result("failed", f"Resend could not be reached ({type(exc).__name__}).", started)
    code = int(response.status_code)
    where = f"the sender's domain ({domain})" if domain else "the sender's domain"
    if code == 401 and _resend_error_name(response) == "restricted_api_key":
        return _result(
            "passed",
            f"Resend recognised the key (sending access only, so the domains cannot be read with it). Check in "
            f"Resend > Domains that {where} is Verified. Nothing was sent.",
            started,
        )
    if code in (401, 403):
        return _result("failed", f"Resend rejected the key (HTTP {code}). Check RESEND_API_KEY.", started)
    if code != 200:
        return _result("failed", f"Resend answered HTTP {code}.", started)
    if not domain:
        return _result(
            "passed",
            "Resend accepted the key. OUTREACH_SENDER_EMAIL is not set, so no sender domain was checked. Nothing was "
            "sent.",
            started,
        )
    try:
        state = _resend_domain_state(response.json(), domain)
    except ValueError:
        state = None
    if state is None:
        return _result("failed", "Resend accepted the key but its answer could not be read.", started)
    if state == "verified":
        return _result("passed", f"Resend accepted the key and {where} is verified. Nothing was sent.", started)
    if state == "absent":
        return _result(
            "failed",
            f"Resend accepted the key, but {where} is not in this Resend account: add it in Resend > Domains and "
            "publish its DNS records. Until then Resend refuses every message.",
            started,
        )
    return _result(
        "failed",
        f"Resend accepted the key, but {where} is not verified yet (status: {state}): publish its DNS records and "
        "verify it in Resend > Domains. Until then Resend refuses every message.",
        started,
    )


def brevo(get: Callable[..., Any] = requests.get) -> dict[str, Any]:
    """Reads the account (GET /v3/account): proves the key without sending anything. The answer (company, e-mail,
    plan) is never echoed: only the outcome."""
    config = brevo_svc.BrevoConfig.from_env()
    if config is None:
        return _result("skipped", "BREVO_API_KEY is not set.")
    started = time.monotonic()
    try:
        response = get(
            f"{brevo_svc.API_ROOT}/account",
            headers={"api-key": config.api_key, "accept": "application/json"},
            timeout=(5, 15),
            allow_redirects=False,
        )
    except requests.Timeout:
        return _result("failed", "Brevo did not answer in time.", started)
    except requests.RequestException as exc:
        return _result("failed", f"Brevo could not be reached ({type(exc).__name__}).", started)
    code = int(response.status_code)
    if code in (401, 403):
        return _result("failed", f"Brevo rejected the key (HTTP {code}). Check BREVO_API_KEY.", started)
    if code != 200:
        return _result("failed", f"Brevo answered HTTP {code}.", started)
    return _result(
        "passed",
        "Brevo accepted the key. Nothing was sent: the sender must also be verified in Brevo for a message to leave.",
        started,
    )


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


MODELS_SHOWN = 8
# Model families a provider lists that cannot write a message (speech, moderation, embeddings): never offered as
# AI_MODEL.
_NOT_CHAT = ("whisper", "tts", "guard", "embed", "orpheus", "playai", "moderation", "audio", "transcribe")


def chat_models(ids: set[str]) -> list[str]:
    """The listed models that can write a message, sorted: what AI_MODEL may be set to."""
    return sorted(i for i in ids if i and not any(word in i.lower() for word in _NOT_CHAT))


def ai(get: Callable[..., Any] = requests.get) -> dict[str, Any]:
    """Asks the provider which models the key can use: proves the key, the address and the model, and generates nothing
    (no token is used, no name or company is sent)."""
    cfg = ai_svc.config()
    if cfg is None:
        return _result("skipped", "AI_PROVIDER and AI_API_KEY are not both set, or the settings are not valid.")
    started = time.monotonic()
    try:
        response = get(f"{cfg.base_url}/models", headers=ai_svc._headers(cfg), timeout=(5, 15), allow_redirects=False)
    except requests.Timeout:
        return _result("failed", f"{cfg.host} did not answer in time.", started)
    except requests.RequestException as exc:
        return _result("failed", f"{cfg.host} could not be reached ({type(exc).__name__}).", started)
    code = int(response.status_code)
    if code in (401, 403):
        return _result("failed", f"{cfg.host} rejected the key (HTTP {code}).", started)
    if code != 200:
        return _result("failed", f"{cfg.host} answered HTTP {code}.", started)
    try:
        items = response.json().get("data") or []
        ids = {str(m.get("id", "")).removeprefix("models/") for m in items if isinstance(m, dict)}
    except (ValueError, AttributeError):
        ids = set()
    if ids and cfg.model not in ids:
        offered = chat_models(ids)
        more = len(offered) - MODELS_SHOWN
        names = ", ".join(offered[:MODELS_SHOWN]) + (f" (+{more} more)" if more > 0 else "")
        hint = f" Set AI_MODEL to one it offers: {names}." if offered else " Set AI_MODEL."
        return _result("failed", f"The key works but {cfg.host} does not list the model {cfg.model}.{hint}", started)
    light = cfg.model_for("light")
    if light != cfg.model and ids and light not in ids:  # not a failure: the short messages fall back to AI_MODEL
        offered = chat_models(ids)
        names = ", ".join(offered[:MODELS_SHOWN])
        return _result(
            "passed",
            f"{cfg.host} accepted the key and lists the model {cfg.model}, but not the light model {light}: the short "
            f"messages (Rapide) will use {cfg.model}. To use a lighter one, set AI_MODEL_LIGHT"
            + (f" to one it offers: {names}." if names else ".")
            + " Nothing was generated.",
            started,
        )
    also = f" and the light model {light}" if light != cfg.model and ids else ""
    return _result(
        "passed", f"{cfg.host} accepted the key and lists the model {cfg.model}{also}. Nothing was generated.", started
    )
