"""Settings > Integrations: one entry per integration, computed from this server's real configuration.

Pure: `build(facts)` takes plain facts and returns the entries; it never reads the environment, opens a socket or
sees a secret. `Facts.env_set` carries variable NAMES that are set and non-empty, never their values, so `needs`
(the names still to set) is exact without anything sensitive crossing this module. The route gathers the facts.

Status vocabulary (the UI maps each to a colour and a label, nothing is hard-coded there):
    ready       works as configured (nothing to check from here, or the check passed)
    unchecked   nothing missing, but only a live test can prove it works: shown with a "Test" button
    partial     works with a limit, or is set but unusable as is
    missing     not configured: the product refuses to act and says what to configure
    blocked     a safety stop or a configuration that makes sends or links fail
    off         deliberately disabled (a feature flag, dry-run) or not needed yet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlsplit

STATUSES = ("ready", "unchecked", "partial", "missing", "blocked", "off")
GROUPS = ("data", "sources", "sending", "inbound", "ai")
TESTABLE = ("database", "osm", "registry", "smtp", "imap", "sendgrid", "twilio")  # run on the server
BROWSER_TESTS = ("geocoder",)  # the browser itself calls this service, so the browser is what must be tested
DOCS = "docs/integrations.md"

# Every variable the entries above refer to: the route reports which of them are set (names only, never values).
TRACKED_ENV = (
    "DATABASE_URL",
    "PUBLIC_BASE_URL",
    "APP_ENV",
    "OVERPASS_ENDPOINTS",
    "FEATURE_EXTERNAL_SOURCES",
    "FEATURE_LIVE_SENDING",
    "SEND_KILL_SWITCH",
    "OUTREACH_SANDBOX",
    "OUTREACH_LIVE_ALLOWLIST",
    "OUTREACH_LIVE_PHONES",
    "OUTREACH_TEST_SINK",
    "FEATURE_DEMO_DATA",
    "OUTREACH_SENDER_NAME",
    "OUTREACH_SENDER_COMPANY",
    "OUTREACH_SENDER_ADDRESS",
    "OUTREACH_SENDER_EMAIL",
    "SMTP_HOST",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_SECURITY",
    "SMTP_PORT",
    "IMAP_HOST",
    "IMAP_USERNAME",
    "IMAP_PASSWORD",
    "IMAP_PORT",
    "IMAP_FOLDER",
    "SENDGRID_API_KEY",
    "SENDGRID_FROM_EMAIL",
    "SENDGRID_WEBHOOK_PUBLIC_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
    "TWILIO_WEBHOOK_URL",
    "EMERGENT_LLM_KEY",
)

DATABASE_KINDS = {
    "supabase_session_pooler": "Supabase · Session pooler",
    "supabase_transaction_pooler": "Supabase · Transaction pooler",
    "supabase_direct": "Supabase · direct connection",
    "render_postgres": "Render PostgreSQL",
    "local": "Local PostgreSQL",
    "other": "PostgreSQL",
}


@dataclass(frozen=True)
class Facts:
    env_set: frozenset[str] = frozenset()  # names of variables that are set and non-empty — never values
    app_env: str = ""
    public_base_url: Optional[str] = None
    database_kind: str = "other"
    database_port: str = ""
    database_ok: bool = False
    database_latency_ms: Optional[int] = None
    overpass_hosts: tuple[str, ...] = ()
    overpass_cooling: tuple[str, ...] = ()
    live_sending: bool = False
    external_sources: bool = False
    kill_switch: bool = False
    sandbox: bool = True
    allowlist_size: int = 0
    phones_size: int = 0  # numbers in OUTREACH_LIVE_PHONES
    test_sink: bool = False  # automated tests only: sends are recorded in-process, never sent
    sender_configured: bool = False
    sender_email: Optional[str] = None
    smtp_configured: bool = False
    smtp_host: Optional[str] = None
    smtp_security: Optional[str] = None
    imap_configured: bool = False
    imap_host: Optional[str] = None
    sendgrid_configured: bool = False
    sendgrid_from: Optional[str] = None
    twilio_configured: bool = False
    twilio_from: Optional[str] = None
    twilio_sid_is_account: bool = True  # an API key (SK…) cannot send; only an account SID (AC…) can
    twilio_signature_ready: bool = False
    sendgrid_signature_ready: bool = False
    ai: dict[str, Any] = field(default_factory=dict)


def _missing(facts: Facts, names: tuple[str, ...]) -> list[str]:
    return [n for n in names if n not in facts.env_set]


def _item(
    id_: str,
    name: str,
    group: str,
    status: str,
    label: str,
    summary: str,
    *,
    env: tuple[str, ...] = (),
    needs: Optional[list[str]] = None,
    facts: Optional[list[tuple[str, str]]] = None,
    test: Optional[str] = None,
    hint: Optional[str] = None,
) -> dict[str, Any]:
    assert status in STATUSES and group in GROUPS
    return {
        "id": id_,
        "name": name,
        "group": group,
        "status": status,
        "label": label,
        "summary": summary,
        "env": list(env),
        "needs": needs if needs is not None else [],
        "facts": [[k, v] for k, v in (facts or [])],
        "test": test,
        "hint": hint,
        "docs": f"{DOCS}#{id_}",
    }


def _database(f: Facts) -> dict[str, Any]:
    kind = DATABASE_KINDS.get(f.database_kind, DATABASE_KINDS["other"])
    facts = [("host.kind", kind), ("port", f.database_port or "default")]
    if f.database_ok:
        facts.append(("latency", f"{f.database_latency_ms} ms" if f.database_latency_ms is not None else "—"))
    hint = None
    status, label = ("ready", "CONNECTED") if f.database_ok else ("blocked", "UNREACHABLE")
    summary = "Every lead, prospect, campaign and event is stored here." + (
        "" if f.database_ok else " The server could not run a query just now."
    )
    if f.database_kind == "supabase_direct":
        status, label = ("partial", "DIRECT CONNECTION") if f.database_ok else (status, label)
        hint = (
            "The direct Supabase host is IPv6 only; a host without IPv6 (Render) cannot reach it: "
            "use the Session pooler (port 5432)."
        )
    elif f.database_kind == "render_postgres":
        hint = (
            "A free Render database is temporary: for permanent storage "
            "point DATABASE_URL at Supabase (Session pooler)."
        )
    elif f.database_kind == "supabase_transaction_pooler":
        hint = "Prefer the Session pooler (port 5432): the transaction pooler (6543) does not keep prepared statements."
    return _item(
        "database",
        "Database",
        "data",
        status,
        label,
        summary,
        env=("DATABASE_URL",),
        facts=facts,
        test="server",
        hint=hint,
    )


def _public_url(f: Facts) -> dict[str, Any]:
    url = (f.public_base_url or "").strip()
    host = (urlsplit(url).hostname or "") if url else ""
    local = host in ("", "localhost", "127.0.0.1")
    production = f.app_env.lower() == "production"
    facts = [
        ("APP_ENV", f.app_env or "not set"),
        ("PUBLIC_BASE_URL", url or "not set (defaults to http://localhost:8000)"),
    ]
    needs = [] if "PUBLIC_BASE_URL" in f.env_set else ["PUBLIC_BASE_URL"]
    summary = "Base of the unsubscribe link in every e-mail: it must be the public address of this API."
    if production and local:
        return _item(
            "public_url",
            "Public URL",
            "data",
            "blocked",
            "UNSUBSCRIBE LINKS POINT NOWHERE",
            summary,
            env=("PUBLIC_BASE_URL", "APP_ENV"),
            needs=needs,
            facts=facts,
        )
    if production and not url.startswith("https://"):
        return _item(
            "public_url",
            "Public URL",
            "data",
            "partial",
            "NOT HTTPS",
            summary,
            env=("PUBLIC_BASE_URL", "APP_ENV"),
            needs=[],
            facts=facts,
        )
    return _item(
        "public_url",
        "Public URL",
        "data",
        "ready",
        "LOCAL" if local else "CONFIGURED",
        summary,
        env=("PUBLIC_BASE_URL", "APP_ENV"),
        needs=[],
        facts=facts,
    )


def _osm(f: Facts) -> dict[str, Any]:
    cooling = list(f.overpass_cooling)
    facts = [("servers", ", ".join(f.overpass_hosts) or "none"), ("cooling down", ", ".join(cooling) or "none")]
    if f.overpass_hosts and len(cooling) >= len(f.overpass_hosts):
        status, label = "partial", "ALL SERVERS COOLING DOWN"
    elif cooling:
        status, label = "partial", f"{len(cooling)} OF {len(f.overpass_hosts)} COOLING DOWN"
    else:
        status, label = "unchecked", "KEYLESS · NOT TESTED"
    return _item(
        "osm",
        "OpenStreetMap (Overpass)",
        "sources",
        status,
        label,
        "Real places for the map search. Public servers, no key; a search that finds none falls back to the browser.",
        env=("OVERPASS_ENDPOINTS",),
        facts=facts,
        test="server",
        hint="Optional: OVERPASS_ENDPOINTS replaces the public servers with your own instance.",
    )


def _geocoder() -> dict[str, Any]:
    return _item(
        "geocoder",
        "City search (api-adresse.data.gouv.fr)",
        "sources",
        "unchecked",
        "KEYLESS · NOT TESTED",
        "Turns a city name into coordinates for the map. Called from your browser, so the test runs in your browser.",
        facts=[("called from", "your browser"), ("key", "none")],
        test="browser",
    )


def _registry(f: Facts) -> dict[str, Any]:
    facts = [("FEATURE_EXTERNAL_SOURCES", "on" if f.external_sources else "off"), ("key", "none")]
    if not f.external_sources:
        return _item(
            "registry",
            "French company registry",
            "sources",
            "off",
            "OFF · FEATURE_EXTERNAL_SOURCES",
            "Public company records as a prospect source. Off by default: network sources need an explicit flag.",
            env=("FEATURE_EXTERNAL_SOURCES",),
            needs=["FEATURE_EXTERNAL_SOURCES"],
            facts=facts,
            test="server",
        )
    return _item(
        "registry",
        "French company registry",
        "sources",
        "unchecked",
        "KEYLESS · NOT TESTED",
        "Public company records (recherche-entreprises.api.gouv.fr) as a prospect source.",
        env=("FEATURE_EXTERNAL_SOURCES",),
        facts=facts,
        test="server",
    )


def _sender(f: Facts) -> dict[str, Any]:
    names = ("OUTREACH_SENDER_NAME", "OUTREACH_SENDER_COMPANY", "OUTREACH_SENDER_ADDRESS", "OUTREACH_SENDER_EMAIL")
    needs = _missing(f, names)
    summary = "Identity, postal address and reply address that every outbound e-mail must carry."
    if f.sender_configured:
        return _item(
            "sender",
            "Sender identity",
            "sending",
            "ready",
            "CONFIGURED",
            summary,
            env=names,
            facts=[("sender.email", f.sender_email or "—")],
        )
    return _item(
        "sender",
        "Sender identity",
        "sending",
        "missing",
        "NOT CONFIGURED",
        summary + " Drafts and sends are refused without it.",
        env=names,
        needs=needs,
    )


def _sending_mode(f: Facts) -> dict[str, Any]:
    facts = [
        ("FEATURE_LIVE_SENDING", "on" if f.live_sending else "off"),
        ("SEND_KILL_SWITCH", "ON" if f.kill_switch else "off"),
        ("OUTREACH_SANDBOX", f"on ({f.allowlist_size} e-mail, {f.phones_size} phone allowed)" if f.sandbox else "off"),
    ]
    env = (
        "FEATURE_LIVE_SENDING",
        "SEND_KILL_SWITCH",
        "OUTREACH_SANDBOX",
        "OUTREACH_LIVE_ALLOWLIST",
        "OUTREACH_LIVE_PHONES",
    )
    summary = "What actually leaves the system. Limits, pause and compliance checks apply to every send path."
    if f.kill_switch:
        return _item(
            "sending_mode",
            "Sending mode",
            "sending",
            "blocked",
            "HALTED BY THE KILL SWITCH",
            summary,
            env=env,
            facts=facts,
        )
    if f.test_sink:
        return _item(
            "sending_mode",
            "Sending mode",
            "sending",
            "partial",
            "TEST SINK · NOTHING IS SENT",
            summary + " Automated tests only: sends are recorded in-process.",
            env=env,
            facts=facts,
        )
    if not f.live_sending:
        return _item(
            "sending_mode", "Sending mode", "sending", "off", "DRY-RUN · NOTHING LEAVES", summary, env=env, facts=facts
        )
    if not f.smtp_configured:
        return _item(
            "sending_mode",
            "Sending mode",
            "sending",
            "blocked",
            "LIVE FLAG ON · SMTP INCOMPLETE",
            summary + " Sends are refused.",
            env=env,
            needs=_missing(f, ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD")),
            facts=facts,
        )
    if f.sandbox:
        return _item(
            "sending_mode",
            "Sending mode",
            "sending",
            "partial",
            "LIVE · SANDBOX",
            summary + " Only allowlisted recipients.",
            env=env,
            facts=facts,
        )
    return _item(
        "sending_mode", "Sending mode", "sending", "ready", "LIVE · REAL E-MAIL", summary, env=env, facts=facts
    )


def _smtp(f: Facts) -> dict[str, Any]:
    names = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD")
    summary = "The real e-mail channel for prospects: TLS is mandatory, the certificate is verified."
    optional = ("SMTP_SECURITY", "SMTP_PORT")
    if f.smtp_configured:
        return _item(
            "smtp",
            "SMTP e-mail",
            "sending",
            "unchecked",
            "CONFIGURED · NOT TESTED",
            summary,
            env=names + optional,
            facts=[("smtp.host", f.smtp_host or "—"), ("security", f.smtp_security or "starttls")],
            test="server",
            hint="The test connects and signs in; it never sends a message.",
        )
    present = [n for n in names if n in f.env_set]
    if present:  # something is set but the whole is unusable (a missing field, or an invalid security / port)
        return _item(
            "smtp",
            "SMTP e-mail",
            "sending",
            "partial",
            "SET BUT UNUSABLE",
            summary + " SMTP_SECURITY must be starttls or ssl and SMTP_PORT a valid port.",
            env=names + optional,
            needs=_missing(f, names),
            test="server",
        )
    return _item(
        "smtp",
        "SMTP e-mail",
        "sending",
        "missing",
        "NOT CONFIGURED",
        summary,
        env=names + optional,
        needs=list(names),
        test="server",
    )


def _imap(f: Facts) -> dict[str, Any]:
    names = ("IMAP_HOST", "IMAP_USERNAME", "IMAP_PASSWORD")
    summary = "Reads replies, hard bounces and STOP requests from the sending mailbox (TLS only, port 993)."
    optional = ("IMAP_PORT", "IMAP_FOLDER")
    if f.imap_configured:
        return _item(
            "imap",
            "IMAP mailbox",
            "sending",
            "unchecked",
            "CONFIGURED · NOT TESTED",
            summary,
            env=names + optional,
            facts=[("imap.host", f.imap_host or "—")],
            test="server",
            hint="The test signs in and opens the folder read-only; it never marks or changes a message.",
        )
    if any(n in f.env_set for n in names):
        return _item(
            "imap",
            "IMAP mailbox",
            "sending",
            "partial",
            "SET BUT UNUSABLE",
            summary,
            env=names + optional,
            needs=_missing(f, names),
            test="server",
        )
    return _item(
        "imap",
        "IMAP mailbox",
        "sending",
        "missing",
        "NOT CONFIGURED",
        summary + " Without it, replies and bounces are handled by hand.",
        env=names + optional,
        needs=list(names),
        test="server",
    )


def _sendgrid(f: Facts) -> dict[str, Any]:
    names = ("SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL")
    summary = "E-mail provider for CRM messages and campaigns (open and click tracking). SMTP is used first when set."
    if f.sendgrid_configured:
        return _item(
            "sendgrid",
            "SendGrid e-mail",
            "sending",
            "unchecked",
            "CONFIGURED · NOT TESTED",
            summary,
            env=names,
            facts=[("from.email", f.sendgrid_from or "—")],
            test="server",
            hint="The test only reads the key's scopes.",
        )
    if f.smtp_configured:  # SMTP already carries the e-mail: SendGrid is an alternative, not a gap
        return _item(
            "sendgrid",
            "SendGrid e-mail",
            "sending",
            "off",
            "NOT NEEDED · SMTP IS USED",
            summary,
            env=names,
            test="server",
        )
    return _item(
        "sendgrid",
        "SendGrid e-mail",
        "sending",
        "missing",
        "NOT CONFIGURED · NOTHING IS SENT",
        summary,
        env=names,
        needs=_missing(f, names),
        test="server",
    )


def _twilio(f: Facts) -> dict[str, Any]:
    names = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM")
    summary = (
        "WhatsApp provider, only to contacts who opted in. Until it is configured nothing is sent or recorded as sent."
    )
    if f.twilio_configured:
        return _item(
            "twilio",
            "Twilio WhatsApp",
            "sending",
            "unchecked",
            "CONFIGURED · NOT TESTED",
            summary,
            env=names,
            facts=[("from.number", f.twilio_from or "default sandbox number")],
            test="server",
            hint="The test only reads the account record.",
        )
    if "TWILIO_ACCOUNT_SID" in f.env_set and not f.twilio_sid_is_account:
        return _item(
            "twilio",
            "Twilio WhatsApp",
            "sending",
            "partial",
            "SID MUST START WITH AC",
            summary + " An API key (SK…) cannot send.",
            env=names,
            needs=_missing(f, ("TWILIO_AUTH_TOKEN",)),
            test="server",
        )
    return _item(
        "twilio",
        "Twilio WhatsApp",
        "sending",
        "missing",
        "NOT CONFIGURED · NOTHING IS SENT",
        summary,
        env=names,
        needs=_missing(f, ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")),
        test="server",
    )


def _twilio_webhook(f: Facts) -> dict[str, Any]:
    names = ("TWILIO_AUTH_TOKEN", "TWILIO_WEBHOOK_URL")
    summary = "Inbound WhatsApp events must be signed by Twilio; an unsigned call is rejected in production."
    if not f.twilio_configured and not f.twilio_signature_ready:
        return _item(
            "twilio_webhook",
            "Twilio webhook signature",
            "inbound",
            "off",
            "NOT NEEDED YET",
            summary + " Needed once Twilio is configured.",
            env=names,
        )
    needs = _missing(f, names)
    if needs:
        return _item(
            "twilio_webhook",
            "Twilio webhook signature",
            "inbound",
            "partial",
            "INCOMPLETE",
            summary,
            env=names,
            needs=needs,
        )
    return _item("twilio_webhook", "Twilio webhook signature", "inbound", "ready", "VERIFIED", summary, env=names)


def _sendgrid_webhook(f: Facts) -> dict[str, Any]:
    names = ("SENDGRID_WEBHOOK_PUBLIC_KEY",)
    summary = "Inbound e-mail events (delivered, bounced, opened) must carry SendGrid's signature."
    if not f.sendgrid_configured and not f.sendgrid_signature_ready:
        return _item(
            "sendgrid_webhook",
            "SendGrid webhook signature",
            "inbound",
            "off",
            "NOT NEEDED YET",
            summary + " Needed once SendGrid is configured.",
            env=names,
        )
    if not f.sendgrid_signature_ready:
        return _item(
            "sendgrid_webhook",
            "SendGrid webhook signature",
            "inbound",
            "partial",
            "NO PUBLIC KEY",
            summary,
            env=names,
            needs=list(names),
        )
    return _item("sendgrid_webhook", "SendGrid webhook signature", "inbound", "ready", "VERIFIED", summary, env=names)


def _ai(f: Facts) -> dict[str, Any]:
    ai = f.ai
    facts = [
        ("api.key", "configured" if ai.get("key_configured") else "not set"),
        ("emergentintegrations", "installed" if ai.get("library_available") else "not installed"),
    ]
    if ai.get("active"):
        return _item(
            "ai",
            "AI composer",
            "ai",
            "ready",
            "LIVE · MODEL CALLED",
            "Messages are written by the model.",
            env=("EMERGENT_LLM_KEY",),
            facts=facts,
        )
    reason = ai.get("reason") or "no model can be called"
    status = "partial" if ai.get("key_configured") else "missing"
    return _item(
        "ai",
        "AI composer",
        "ai",
        status,
        "OFF · NOTHING IS GENERATED",
        f"No model is called and no canned text is offered in its place. Reason: {reason}.",
        env=("EMERGENT_LLM_KEY",),
        needs=[] if ai.get("key_configured") else ["EMERGENT_LLM_KEY"],
        facts=facts,
        hint=(
            None
            if ai.get("key_configured")
            else "Calling a model is billed by its provider; nothing calls one until a key is set."
        ),
    )


def build(f: Facts) -> dict[str, Any]:
    items = [
        _database(f),
        _public_url(f),
        _osm(f),
        _geocoder(),
        _registry(f),
        _sender(f),
        _sending_mode(f),
        _smtp(f),
        _imap(f),
        _sendgrid(f),
        _twilio(f),
        _twilio_webhook(f),
        _sendgrid_webhook(f),
        _ai(f),
    ]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
    return {"items": items, "counts": counts, "total": len(items)}
