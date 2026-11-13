"""Pydantic models for the Plantiers - OutreachOS platform."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------ Auth & Org ------------------------
class Organization(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    name: str
    plan: Literal["free", "pro", "enterprise"] = "pro"
    created_at: datetime = Field(default_factory=_now)


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    email: EmailStr
    full_name: str
    org_id: str
    role: Literal["owner", "admin", "member"] = "owner"
    created_at: datetime = Field(default_factory=_now)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    organization_name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
    organization: Organization


# ------------------------ Leads / CRM ------------------------
LeadStage = Literal["new", "contacted", "engaged", "qualified", "won", "lost"]


ConsentStatus = Literal["opted_in", "opted_out", "unknown"]


class HeatOut(BaseModel):
    """Why a lead ranks where it does: real information and the score, never an invented figure."""

    value: int  # 0..100
    tier: Literal["hot", "warm", "cold"]
    info_pct: int  # share of the 8 tracked fields that are really known
    known: List[str]
    missing: List[str]
    scored: bool  # False: never scored, ranked on information alone
    top: bool  # heat >= 80: the leads to work first
    has_contact: bool  # at least one of e-mail, phone, website is really known; False = an empty lead
    score: Optional[int] = None


class Lead(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    country: Optional[str] = None
    language: str = "en"
    stage: LeadStage = "new"
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    notes: Optional[str] = None
    score: int = 0
    email_consent: ConsentStatus = "unknown"
    whatsapp_consent: ConsentStatus = "unknown"
    created_at: datetime = Field(default_factory=_now)
    city: Optional[str] = None
    website: Optional[str] = None
    vertical: Optional[str] = None
    heat: Optional[HeatOut] = None
    website_quality: Optional[int] = None
    digital_maturity: Optional[int] = None
    fit_score: Optional[int] = None
    priority: Optional[Literal["low", "medium", "high"]] = None
    qualification_scored_at: Optional[datetime] = None
    enrichment_status: Literal["completed", "required"] = "required"
    # A prospect found by discovery (map, sources, import) says where it stands in the human review; a CRM lead: none.
    review_status: Optional[Literal["pending", "approved", "rejected"]] = None


class LeadCreate(BaseModel):
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    country: Optional[str] = None
    language: str = "en"
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    notes: Optional[str] = None
    # Consent captured at ingestion time (e.g. a CSV column, a form checkbox).
    # Anything else (manual opt-in later, unsubscribe webhooks) goes through
    # POST /api/leads/{id}/consent instead of this one-shot flag.
    email_opt_in: bool = False
    whatsapp_opt_in: bool = False
    consent_source: Optional[str] = None


class ScoreLeadsIn(BaseModel):
    lead_ids: List[uuid.UUID] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def lead_ids_are_unique(self):
        if len(self.lead_ids) != len(set(self.lead_ids)):
            raise ValueError("lead_ids must not contain duplicates")
        return self


class ScoreLeadsQueued(BaseModel):
    job_id: str
    status: Literal["queued"]
    lead_count: int


class JobRunOut(BaseModel):
    id: str
    job_type: str
    status: Literal["queued", "running", "succeeded", "partial", "failed"]
    total_items: int
    processed_items: int
    failed_items: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    country: Optional[str] = None
    stage: Optional[LeadStage] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    score: Optional[int] = None


class ConsentUpdateIn(BaseModel):
    channel: Literal["email", "whatsapp"]
    status: ConsentStatus
    source: str = "manual"


# ------------------------ Campaigns ------------------------
CampaignStatus = Literal["draft", "running", "paused", "completed"]
Channel = Literal["email", "whatsapp"]


def _default_channels() -> List[Channel]:
    return ["email"]


class CampaignStep(BaseModel):
    id: str = Field(default_factory=_uid)
    channel: Channel = "email"
    delay_hours: int = 0
    subject: Optional[str] = None
    body: str = ""
    language: str = "en"


class Campaign(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    name: str
    goal: Optional[str] = None
    status: CampaignStatus = "draft"
    channels: List[Channel] = Field(default_factory=_default_channels)
    steps: List[CampaignStep] = Field(default_factory=list)
    lead_ids: List[str] = Field(default_factory=list)
    agent_id: Optional[str] = None
    sent: int = 0
    opened: int = 0
    replied: int = 0
    converted: int = 0
    created_at: datetime = Field(default_factory=_now)


class CampaignCreate(BaseModel):
    name: str
    goal: Optional[str] = None
    channels: List[Channel] = Field(default_factory=_default_channels)
    steps: List[CampaignStep] = Field(default_factory=list)
    lead_ids: List[str] = Field(default_factory=list)
    agent_id: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    status: Optional[CampaignStatus] = None
    channels: Optional[List[Channel]] = None
    steps: Optional[List[CampaignStep]] = None
    lead_ids: Optional[List[str]] = None
    agent_id: Optional[str] = None


# ------------------------ Agents ------------------------
AgentStatus = Literal["idle", "running", "paused", "error"]


class Agent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    name: str
    role: str = "outreach"  # outreach / enrichment / scraper / responder
    status: AgentStatus = "idle"
    tasks_completed: int = 0
    tasks_in_queue: int = 0
    last_heartbeat: datetime = Field(default_factory=_now)
    created_at: datetime = Field(default_factory=_now)


class AgentCreate(BaseModel):
    name: str
    role: str = "outreach"


# ------------------------ Messages ------------------------
MessageStatus = Literal["queued", "sent", "delivered", "opened", "replied", "failed", "mock"]


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    campaign_id: Optional[str] = None
    lead_id: Optional[str] = None
    channel: Channel
    direction: Literal["outbound", "inbound"] = "outbound"
    to: str
    subject: Optional[str] = None
    body: str
    status: MessageStatus = "queued"
    provider_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class SendEmailIn(BaseModel):
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    to: EmailStr
    subject: str
    body: str


class SendWhatsAppIn(BaseModel):
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    to: str  # +1234567890
    body: str


# ------------------------ AI ------------------------
class AIGenerateIn(BaseModel):
    recipient_name: str
    company: Optional[str] = None
    product: str
    language: str = "en"
    tone: Literal["professional", "friendly", "casual", "urgent", "concise"] = "professional"
    channel: Channel = "email"
    goal: Optional[str] = None
    opportunity: Optional[str] = None


class AIGenerateOut(BaseModel):
    subject: Optional[str] = None
    body: str
    whatsapp: Optional[str] = None
    language: str
    opportunity: Optional[str] = None


# ------------------------ Activity Feed ------------------------
class Activity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    kind: str
    title: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


# ------------------------ CRM: Notes, Tasks, Tags ------------------------
TaskStatus = Literal["open", "in_progress", "done", "cancelled"]


class Note(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    author_user_id: str
    body: str
    created_at: datetime = Field(default_factory=_now)


class NoteCreate(BaseModel):
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    body: str

    @model_validator(mode="after")
    def _require_a_target(self) -> "NoteCreate":
        if not self.lead_id and not self.campaign_id:
            raise ValueError("lead_id or campaign_id is required")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    title: str
    status: TaskStatus = "open"
    due_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_now)


class TaskCreate(BaseModel):
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    title: str
    due_at: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[TaskStatus] = None
    assigned_to_user_id: Optional[str] = None
    due_at: Optional[datetime] = None


class Tag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    org_id: str
    name: str
    color: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class TagCreate(BaseModel):
    name: str
    color: Optional[str] = None


# ------------------------ Settings ------------------------
class AIStatus(BaseModel):
    key_configured: bool = False
    provider: Optional[str] = None  # groq | gemini | mistral | custom
    model: Optional[str] = None
    host: Optional[str] = None  # where names and companies go when a message is written (never the key)
    active: bool = False  # True only when the model is really called
    mode: str = "off"  # "live" | "off" (nothing is generated)
    reason: Optional[str] = None  # why it is off


class OutreachStatus(BaseModel):
    dry_run: bool = True
    live_sending_flag: bool = False
    kill_switch: bool = False
    sender_configured: bool = False
    sender_email: Optional[str] = None
    smtp_configured: bool = False  # SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD are all set and valid
    smtp_host: Optional[str] = None  # never the username or the password
    sandbox: bool = True  # live sending only reaches OUTREACH_LIVE_ALLOWLIST while this is true
    allowlist_size: int = 0
    imap_configured: bool = False  # IMAP_HOST, IMAP_USERNAME and IMAP_PASSWORD are set: replies and bounces are read
    imap_host: Optional[str] = None  # never the username or the password


class WebhookStatus(BaseModel):
    production: bool = False
    twilio_signature_ready: bool = False  # TWILIO_AUTH_TOKEN is set
    twilio_webhook_url_set: bool = False
    sendgrid_signature_ready: bool = False  # SENDGRID_WEBHOOK_PUBLIC_KEY is set


class IntegrationItem(BaseModel):
    """One integration, computed from the real configuration: names of variables only, never a value."""

    id: str
    name: str
    group: Literal["data", "sources", "sending", "inbound", "ai"]
    status: Literal["ready", "unchecked", "partial", "missing", "blocked", "off"]
    label: str
    summary: str
    env: List[str] = Field(default_factory=list)  # every variable that controls it
    needs: List[str] = Field(default_factory=list)  # the ones still to set
    facts: List[List[str]] = Field(default_factory=list)  # [key, value] pairs, never secret
    test: Optional[Literal["server", "browser"]] = None  # where its live test runs
    hint: Optional[str] = None
    docs: str


class IntegrationTestOut(BaseModel):
    id: str
    ok: bool
    outcome: Literal["passed", "failed", "skipped"]
    latency_ms: Optional[int] = None
    detail: str
    checked_at: datetime


class IntegrationSettings(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_account_sid_configured: bool = False
    sendgrid_configured: bool = False
    ai: AIStatus = Field(default_factory=AIStatus)
    outreach: OutreachStatus = Field(default_factory=OutreachStatus)
    webhooks: WebhookStatus = Field(default_factory=WebhookStatus)
    items: List[IntegrationItem] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)
    generated_at: Optional[datetime] = None


class SettingsUpdate(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None


# ------------------------ OutreachOS prospects ------------------------
class QueueCountsOut(BaseModel):
    hot: int
    warm: int
    cold: int
    total: int
    top: int  # the hot ones at 80 or more
    empty: int  # leads with no e-mail, phone or website in this queue: left out of the figures above when `hide_empty`


class ProspectSummary(BaseModel):
    id: str
    name: str
    city: Optional[str] = None
    vertical: Optional[str] = None
    website: Optional[str] = None
    review_status: Literal["pending", "approved", "rejected"]
    score: Optional[int] = None  # None = never scored
    coverage: Optional[float] = None  # share of weighted signals that could be observed
    created_at: datetime
    heat: Optional[HeatOut] = None


class ProspectList(BaseModel):
    items: List[ProspectSummary]
    total: int


class SignalOut(BaseModel):
    key: str
    label: str
    state: str  # unknown | detected | not_detected (enforced by a CHECK constraint)
    evidence: str
    observed_at: datetime
    dismissed: bool = False  # a reviewer marked this signal as wrong: it reads as unknown in the score and the drafts
    dismissed_reason: Optional[str] = None
    observed_state: Optional[str] = None  # the state as observed, when it differs from `state` because of a dismissal


class DismissIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class DismissOut(BaseModel):
    signal: "SignalOut"
    score: "ScoreOut"


class CampaignRescoreOut(BaseModel):
    total: int
    prospects_rescored: int
    crm_leads_rescored: int
    skipped: int


class SourceOut(BaseModel):
    id: str
    source_name: str
    source_url: str
    external_id: str
    license_note: str
    fetched_at: datetime
    fields: dict


class ScoreOut(BaseModel):
    score: int
    coverage: float
    version: int
    config_label: str
    config_hash: str
    computed_at: datetime
    breakdown: List[dict]


class DraftOut(BaseModel):
    id: str
    channel: str
    subject: str
    body: str
    facts: List[str]
    template_version: str
    status: str  # draft | approved | rejected (enforced by a CHECK constraint)
    dry_run: bool
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    # `body` is `message` + `footer`: the person edits the message; the footer (sender coordinates, data origin,
    # unsubscribe link) is rebuilt by the server on every save and can neither be edited nor dropped.
    message: str = ""
    footer: str = ""
    edited_at: Optional[datetime] = None


class DraftEditIn(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=8000)


class ProspectDetail(ProspectSummary):
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    sources: List[SourceOut]
    signals: List[SignalOut]
    score_detail: Optional[ScoreOut] = None
    drafts: List[DraftOut]
    reviewed_at: Optional[datetime] = None


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: Optional[str] = Field(default=None, max_length=1000)


class DiscoveryRunIn(BaseModel):
    source: str = "fixture_directory"


class DiscoveryRunOut(BaseModel):
    dry_run: bool
    source: str
    listings_found: int
    entities: int
    duplicates_merged: int
    suppressed: int
    prospects_created: int
    prospects_updated: int
    sources_recorded: int
    sites_checked: int
    signals_recorded: int
    scores_recorded: int


class ScoreConfigIO(BaseModel):
    label: str = Field(default="custom", min_length=1, max_length=80)
    weights: dict[str, int]
    stale_days: int = Field(default=365, ge=30, le=3650)


class ScoreConfigOut(ScoreConfigIO):
    version: int
    config_hash: str
    rescored: int = 0


# ------------------------ Dashboard ------------------------
class DashboardOut(BaseModel):
    generated_at: datetime
    kpis: dict
    series: List[dict]
    latest_prospects: List[dict]
    latest_signals: List[dict]
    campaigns: List[dict]
    limits: dict
    inbox: List[dict]
    top_signals: List[dict] = Field(default_factory=list)
    geography: dict = Field(default_factory=dict)


# ------------------------ Prospect list import ------------------------
LegalBasis = Literal["legitimate_interest_b2b", "consent", "contract", "other"]


class ImportIn(BaseModel):
    format: Literal["csv", "json"]
    content: str = Field(min_length=1, max_length=2_100_000)
    filename: Optional[str] = Field(default=None, max_length=200)
    origin: str = Field(min_length=10, max_length=1000, description="Where the list comes from, in words")
    legal_basis: LegalBasis
    legal_basis_note: Optional[str] = Field(default=None, max_length=1000)
    country: str = Field(default="FR", pattern="^[A-Z]{2}$")
    language: str = Field(default="fr", pattern="^[a-z]{2}$")
    vertical: str = Field(default="unspecified", min_length=1, max_length=60)
    preview: bool = True  # nothing is written until `preview` is false AND `attestation` is true
    attestation: bool = False  # "I have the right to use this list for B2B prospecting on the stated basis"
    # Look at each company's own public homepage (robots.txt respected). Needs FEATURE_EXTERNAL_SOURCES; off by default.
    check_websites: bool = False


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportOut(BaseModel):
    preview: bool
    batch_id: Optional[str] = None
    rows_total: int
    rows_valid: int
    errors_count: int
    errors: List[ImportRowError] = Field(default_factory=list)  # first 50 only
    ignored_columns: List[str] = Field(default_factory=list)
    entities: int
    duplicates_merged: int
    suppressed: int
    created: int  # preview: would create
    updated: int  # preview: would update (already known prospects)
    sites_checked: int = 0  # homepages really fetched (the others stay "not checked", never "bad")
    already_imported: bool = False  # a file with the same content was imported before


class ImportBatchOut(BaseModel):
    id: str
    created_at: datetime
    filename: Optional[str] = None
    format: str
    origin: str
    legal_basis: str
    legal_basis_note: Optional[str] = None
    rows_total: int
    source_name: str
    summary: dict


class SuppressionIn(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    domain: Optional[str] = None

    @model_validator(mode="after")
    def _one_identity(self):
        if not (self.email or self.phone or self.domain):
            raise ValueError("provide at least one of email, phone, domain")
        return self


class SuppressionOut(BaseModel):
    added: int


class ProspectEventOut(BaseModel):
    id: str
    action: str
    actor_type: str
    actor_user_id: Optional[str] = None
    detail: dict
    created_at: datetime


class OutreachSettingsOut(BaseModel):
    flags: dict[str, bool]
    sender_configured: bool
    usage: dict[str, int]
    active_score_version: Optional[int] = None


# ------------------------ Outbound dispatch (dry-run) ------------------------
class DispatchIn(BaseModel):
    draft_id: str


class OutboundMessageOut(BaseModel):
    id: str
    lead_id: str
    draft_id: Optional[str] = None
    channel: str
    to_email: Optional[str] = None
    subject: str
    status: str  # sending | sent | failed | bounced | replied (sending = outcome not yet known)
    dry_run: bool
    adapter: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    dispatched_at: datetime
    created: bool = True  # False when an idempotent replay returned an existing message


class OutboundEventOut(BaseModel):
    id: str
    event_type: str
    detail: dict
    created_at: datetime


class OutboundMessageDetail(OutboundMessageOut):
    body: str
    events: List[OutboundEventOut]


class SmtpCheckIn(BaseModel):
    to: EmailStr


class WhatsAppCheckIn(BaseModel):
    to: str = Field(min_length=8, max_length=20, description="E.164 number, e.g. +33612345678")


class WhatsAppCheckOut(BaseModel):
    status: str  # sent | failed
    to: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


class InboxSyncOut(BaseModel):
    fetched: int = 0
    replies: int = 0
    opt_outs: int = 0
    bounces: int = 0
    duplicates: int = 0
    unmatched: int = 0
    ignored: int = 0


class SmtpCheckOut(BaseModel):
    status: str  # sent | failed | unknown
    to: str
    adapter: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


class SimulateIn(BaseModel):
    event: Literal["bounced", "replied"]
    text: Optional[str] = Field(default=None, max_length=5000)


class LimitsPatch(BaseModel):
    max_per_day: Optional[int] = Field(default=None, ge=0, le=100000)
    max_per_hour: Optional[int] = Field(default=None, ge=0, le=100000)
    min_delay_seconds: Optional[int] = Field(default=None, ge=0, le=86400)
    sending_paused: Optional[bool] = None


class LimitsOut(BaseModel):
    max_per_day: int
    max_per_hour: int
    min_delay_seconds: int
    sending_paused: bool


class SendStatusOut(BaseModel):
    dry_run: bool
    kill_switch: bool
    paused: bool
    limits: LimitsOut
    sent_today: int
    sent_last_hour: int
    last_dispatched_at: Optional[datetime] = None
    next_allowed_at: Optional[datetime] = None
    blocked_by: Optional[str] = None


class MapSearchIn(BaseModel):
    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    category: str = Field(min_length=1, max_length=40)


class MapFallbackOut(BaseModel):
    query: str  # the Overpass query for this job, to be sent by the browser to one of `endpoints`
    endpoints: List[str]


class MapJobOut(BaseModel):
    id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    category: str
    south: float
    west: float
    north: float
    east: float
    source: Literal["overpass", "overpass_browser", "cache"]
    result_count: int
    truncated: bool
    cache_hit: bool
    error_code: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    fallback: Optional[MapFallbackOut] = None  # only on a failed search whose cause is the public servers


class MapParseIn(BaseModel):
    data: dict  # the Overpass JSON answer, fetched by the browser


class MapPlaceOut(BaseModel):
    external_id: str  # OpenStreetMap node/way/relation id
    name: str
    category: Optional[str] = None
    lat: float
    lon: float
    address: Optional[str] = None
    postcode: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None  # only what the contributors published
    email: Optional[str] = None  # idem; null means "not published", not "none exists"
    website: Optional[str] = None
    source_url: str


class MapPlaceIn(BaseModel):
    """One place exactly as the map showed it (only what contributors published); the server re-validates it."""

    external_id: str = Field(min_length=3, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    category: Optional[str] = Field(default=None, max_length=60)
    address: Optional[str] = Field(default=None, max_length=300)
    postcode: Optional[str] = Field(default=None, max_length=20)
    city: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=60)
    email: Optional[str] = Field(default=None, max_length=200)
    website: Optional[str] = Field(default=None, max_length=300)
    source_url: str = Field(min_length=10, max_length=300)


class MapAddIn(BaseModel):
    place: MapPlaceIn
    attestation: bool = False  # "I may use these professional contact details for B2B prospecting"
    check_website: bool = True  # look for a public e-mail on the business's OWN site (robots.txt respected)
    approve: bool = True  # the person adding it decides now: it joins the CRM; false = waits in the review queue
    country: str = Field(default="FR", pattern="^[A-Z]{2}$")


class MapAddManyIn(BaseModel):
    """One click on the map's selection: every place joins the CRM (or the review queue), with the same attested import."""

    places: List[MapPlaceIn] = Field(min_length=1, max_length=200)
    attestation: bool = False  # "I may use these professional contact details for B2B prospecting"
    approve: bool = True  # the person's own decision: they join the CRM; false = they wait in the review queue
    check_website: bool = False  # read each business's own site for a public e-mail (capped by the importer)
    country: str = Field(default="FR", pattern="^[A-Z]{2}$")


class MapAddManyOut(BaseModel):
    requested: int
    created: int  # new prospects
    already_known: int  # already one of your prospects: completed, never duplicated
    in_crm: int  # approved now or before: in the CRM pipeline
    waiting_review: int  # added but left in the review queue (approve=false)
    kept_rejected: int  # a person rejected it before: a bulk click never overrides that decision
    suppressed: int  # on the suppression list: not added, never approved
    unreadable: int  # a row the importer could not read
    sites_checked: int
    lead_ids: List[str]


class MapAddOut(BaseModel):
    lead_id: str
    name: str
    created: bool  # false: it was already one of your prospects (details completed, nothing duplicated)
    review_status: Literal["pending", "approved", "rejected"]
    in_crm: (
        bool  # approved: the person decided it joins the CRM pipeline (a pending one is listed too, marked "to review")
    )
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email_found_on_site: bool = False  # the address came from the business's own site, not from the map
    website_checked: bool = False  # the homepage was really fetched (never "not found" when it was not read)
    heat: Optional[HeatOut] = None


class MapSearchOut(BaseModel):
    attribution: str
    license_note: str
    truncated: bool = False  # the area held more places than the cap: zoom in to see the rest
    places: List[MapPlaceOut]


class MapProspectOut(BaseModel):
    id: str
    name: str
    city: Optional[str] = None
    lat: float
    lon: float
    review_status: Literal["pending", "approved", "rejected"]
    has_email: bool
    external_id: Optional[str] = None  # the source's id (e.g. OpenStreetMap node/123): lets the map hide duplicates
    vertical: Optional[str] = None
    country: Optional[str] = None
    score: Optional[int] = None  # None = not scored (never 0)
    signals: List[str] = Field(default_factory=list)  # keys detected now; a dismissed signal does not count
    created_at: Optional[datetime] = None
    heat: Optional[dict] = None  # {value, tier, info_pct}: the hottest prospects are listed first on the map
    # The map draws only prospects the common eligibility policy qualifies (the server decides, before the limit):
    # e-mail, phone, address and position on a fresh source, a fit score. A website or WhatsApp is never required.
    address: Optional[str] = None
    eligible: bool = True
    map_ready: bool = False  # kept for older clients: same meaning as `eligible`
    priority: Literal["qualified", "hot"] = "qualified"  # "hot" only with an observed, sourced commercial intent
    priority_label: Optional[str] = None
    fit_score: Optional[int] = None
    has_phone: bool = False
    has_website: bool = False
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None


class OfferIn(BaseModel):
    """What the organisation sells: the only offer an automatic draft may talk about (never invented)."""

    name: str = Field(min_length=2, max_length=120)
    pitch: str = Field(min_length=20, max_length=600)  # what it brings to the customer, in the organisation's words
    cta: str = Field(min_length=3, max_length=160)  # the one simple next step the message asks for
    language: Literal["fr", "en"] = "fr"  # the campaign language, used when the prospect gives no hint of its own


class OfferOut(BaseModel):
    configured: bool
    offer: Optional[OfferIn] = None


class DraftJobOut(BaseModel):
    """The state of the automatic draft of one prospect. A draft is a proposal: it is never sent by this flow."""

    id: str
    lead_id: str
    status: Literal["queued", "generating", "ready", "failed", "unavailable", "offer_required"]
    site_state: Literal["site_found", "site_unreachable", "none_identified", "unknown"]
    language: str
    attempts: int
    error_code: Optional[str] = None
    error: Optional[str] = None  # a sentence for the person
    draft_id: Optional[str] = None
    updated_at: Optional[datetime] = None


class DraftJobSummary(BaseModel):
    counts: dict[str, int]  # prospects by the state of their latest draft job
    offer_configured: bool
    ai_active: bool  # the provider is configured; false = jobs wait as "unavailable" and resume when it is


class DraftListItem(BaseModel):
    """One draft in the Outreach list: where it stands (the review itself is on the prospect's sheet)."""

    id: str
    lead_id: str
    lead_name: str
    city: Optional[str] = None
    subject: str
    status: Literal["draft", "approved", "rejected"]
    auto: bool  # prepared by the automatic flow (AI), as opposed to written by a person
    edited: bool  # a person changed the text
    dry_run: bool
    created_at: datetime


class DraftListPage(BaseModel):
    items: List[DraftListItem]
    total: int
    limit: int
    offset: int


class ToEnrichItem(BaseModel):
    """A discovery prospect kept in the "to enrich" queue: not contactable by default, with what is missing."""

    id: str
    name: str
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    review_status: Optional[str] = None
    fit_score: Optional[int] = None
    missing_fields: List[str] = Field(default_factory=list)  # eligibility.MISSING_FIELDS codes
    created_at: Optional[datetime] = None


class ToEnrichPage(BaseModel):
    items: List[ToEnrichItem]
    total: int
    limit: int
    offset: int


class CityHeatOut(BaseModel):
    """Leads of one town by heat tier, counted (the town search of the map shows them next to each suggestion)."""

    city: str  # the most used spelling
    key: str  # accent- and case-insensitive key (`Saint-Étienne` = `st etienne`) the page matches on
    hot: int
    warm: int
    cold: int
    total: int
    ready: int = 0  # qualified by the common eligibility policy (what the map draws)
    site: int = 0  # of those, with a website too


class LeadSuggestionOut(BaseModel):
    """A lead worth a person's time today: qualified by the common eligibility policy (e-mail, phone, address)."""

    id: str
    name: str
    company: Optional[str] = None
    city: Optional[str] = None
    kind: Literal["prospect", "lead"]  # a discovery prospect (reviewed by a human) or a CRM lead
    review_status: Optional[str] = None  # None for a CRM lead
    heat: dict  # {value, tier, info_pct}
    priority: Literal["qualified", "hot"] = "qualified"  # "hot" only with an observed, sourced commercial intent
    phone: str
    email: str
    website: Optional[str] = None


class FocusOut(BaseModel):
    """What to do next, computed from the organisation's own data at the time of the request."""

    generated_at: datetime
    zones: List[CityHeatOut]  # towns holding the most hot leads that can be called and e-mailed
    leads: List[LeadSuggestionOut]  # the hottest of them, website first


class SourceInfo(BaseModel):
    name: str
    label: str
    kind: Literal["local", "network"]
    available: bool  # network providers need FEATURE_EXTERNAL_SOURCES
    unavailable_reason: Optional[str] = None
    verticals: List[str]
    needs_position: bool
    max_radius_m: int
    rate_limit_per_minute: int
    rate_limit_note: str
    license_note: str
    cost: str = "free, no key"


class DiscoverIn(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    vertical: str = Field(min_length=1, max_length=40)
    limit: int = Field(default=25, ge=1, le=100)
    country: Optional[str] = Field(default=None, pattern="^[A-Z]{2}$")
    city: Optional[str] = Field(default=None, min_length=1, max_length=80)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_m: int = Field(default=5000, ge=100, le=20_000_000)


class DiscoveredSignal(BaseModel):
    key: str
    state: Literal["unknown", "detected", "not_detected"]
    evidence: str


class DiscoveredPlace(BaseModel):
    external_id: str
    name: str
    category: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    source_name: str
    source_url: str
    last_updated: Optional[str] = None
    signals: List[DiscoveredSignal]


class DiscoverOut(BaseModel):
    run_id: str
    provider: str
    license_note: str
    total: int
    duplicates_merged: int
    truncated: bool
    offset: int
    limit: int
    places: List[DiscoveredPlace]


class AddFromRunIn(BaseModel):
    external_ids: List[str] = Field(min_length=1, max_length=100)
    attestation: bool = False  # "I may use these professional details for B2B prospecting (legitimate interest)"
    check_websites: bool = False


class AddFromRunOut(BaseModel):
    created: int
    updated: int
    duplicates_merged: int
    suppressed: int
    sites_checked: int


class SuggestionOut(BaseModel):
    id: str
    kind: Literal["segment", "signal", "hot", "new_leads"]
    title: str
    angle: Optional[str] = None
    rationale: str  # counted facts only
    total: int
    eligible: int  # can join a campaign today
    pending_review: int
    hot: int
    with_email: int
    with_phone: int
    avg_heat: int
    priority: int
    examples: List[str]
    blocked_reason: Optional[str] = None


class SuggestionsOut(BaseModel):
    generated_at: datetime
    dry_run: bool
    basis: dict  # {"prospects": n, "leads": n}: what the suggestions were computed from
    items: List[SuggestionOut]


class SuggestionCreateOut(BaseModel):
    campaign_id: str
    name: str
    assigned: int
    left_out: int
    note: str


# ---------------------------------------------------------------- individual campaigns ("launches")
class LaunchCreateIn(BaseModel):
    name: str = Field(default="Campagne individuelle", min_length=2, max_length=120)
    size: int = Field(default=100, ge=1, le=100)


class LaunchTopUpIn(BaseModel):
    size: int = Field(default=100, ge=1, le=100)


class LaunchScheduleIn(BaseModel):
    expected_count: int = Field(
        ge=0, le=100
    )  # the number the person was shown: refused if it is no longer the real one


class LaunchReviewIn(BaseModel):
    draft_ids: List[str] = Field(min_length=1, max_length=100)
    decision: Literal["approve", "reject"]


class LaunchProviderOut(BaseModel):
    id: str
    label: str
    host: Optional[str] = None
    cold_outreach: Literal["opt_in_required", "unverified", "not_configured"]
    restriction: str


class LaunchGatesOut(BaseModel):
    """What stands between a planned message and the network, right now. Names and numbers only: never a secret."""

    provider: LaunchProviderOut
    dry_run: bool
    live: bool
    kill_switch: bool
    paused: bool
    sandbox: bool
    allowlist_size: int
    sender_configured: bool
    smtp_complete: bool
    max_per_day: int
    max_per_hour: int
    min_delay_seconds: int
    window_start_hour: int
    window_end_hour: int
    timezone: str
    timezone_source: Literal["lead_country", "account_default"] = "lead_country"  # whose zone the window is read in
    sent_today: int
    sent_last_hour: int
    next_allowed_at: Optional[datetime] = None
    scheduler: Dict[str, Any] = Field(
        default_factory=dict
    )  # worker and beat seen or not: the plan only runs if they run


class LaunchExcludedOut(BaseModel):
    lead_id: str
    name: str
    city: Optional[str] = None
    email: Optional[str] = None
    code: str
    label: str


class LaunchOut(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    recipients: int
    planned: int = 0
    sent: int = 0


class LaunchCreatedOut(BaseModel):
    launch: LaunchOut
    requested: int
    selected: int
    scanned: int
    not_approved: int  # prospects still waiting for a person's validation (not listed: they are not candidates)
    excluded: List[LaunchExcludedOut]


class LaunchOverviewOut(BaseModel):
    launch: LaunchOut
    stages: Dict[str, int]  # excluded | no_draft | to_review | rejected | blocked | ready | planned | launched
    exclusions: Dict[str, int]
    exclusion_labels: Dict[str, str]
    dispatch: Dict[str, int]
    draft_jobs: Dict[str, int]  # the automatic draft of the recipients still missing, by state
    gates: LaunchGatesOut


class LaunchRowOut(BaseModel):
    lead_id: str
    name: str
    city: Optional[str] = None
    email: Optional[str] = None
    stage: str
    exclusion: Optional[Dict[str, str]] = None
    draft: Optional[Dict[str, Any]] = None
    draft_job: Optional[Dict[str, Any]] = None
    evidence: Dict[str, Any]
    authorization: Dict[str, Any]
    problems: List[Dict[str, Any]]
    dispatch: Optional[Dict[str, Any]] = None


class LaunchReviewPageOut(BaseModel):
    total: int
    items: List[LaunchRowOut]


class LaunchPlanOut(BaseModel):
    selected: int
    sendable: int
    stages: Dict[str, int]
    exclusions: Dict[str, int]
    exclusion_labels: Dict[str, str]
    schedule: Dict[str, Any]
    blockers: List[Dict[str, str]]
    warnings: List[Dict[str, str]]
    gates: LaunchGatesOut
    generated_at: datetime
    scheduled: Optional[int] = None  # set by POST /schedule: how many were planned


class LaunchTrackingRowOut(BaseModel):
    lead_id: str
    name: str
    city: Optional[str] = None
    email: str
    state: str
    label: str
    reason: Optional[str] = None
    planned_at: datetime
    dispatched_at: Optional[datetime] = None
    adapter: Optional[str] = None
    dry_run: Optional[bool] = None


class LaunchTrackingOut(BaseModel):
    counts: Dict[str, int]
    labels: Dict[str, str]
    total: int
    items: List[LaunchTrackingRowOut]


# ---------------------------------------------------------------- journey: zone -> draft -> approval
class JourneyZoneIn(BaseModel):
    """The perimeter drawn on the map: a box and the category. The server refuses an oversized or inverted one."""

    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    category: str = Field(min_length=1, max_length=40)
    label: Optional[str] = Field(default=None, max_length=80)


class JourneyCreateIn(BaseModel):
    name: str = Field(default="Campagne par zone", min_length=2, max_length=120)
    zone: JourneyZoneIn
    size: int = Field(default=100, ge=1, le=100)


class JourneyTemplateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)


class JourneyApproveIn(BaseModel):
    content_hash: str = Field(min_length=4, max_length=64)  # the template the person read
    expected_count: int = Field(ge=0, le=100)  # the number of messages the person was shown


class JourneyRevokeIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


class JourneyOut(BaseModel):
    """A flexible, server-computed document (summary, progress, readiness): the screen reads what it needs."""

    data: Dict[str, Any]


class JourneyListOut(BaseModel):
    items: List[Dict[str, Any]]


# ---------------------------------------------------------------- bounded automatic mode ("Automatisation max")
class MandateStopRulesIn(BaseModel):
    """The configurable stop rules (the others - kill switch, authentication error, replies not read, change of
    template/zone/offer/sender/provider, expiry, total cap - are fixed and cannot be switched off)."""

    max_bounce_rate: float = Field(default=0.05, gt=0, le=0.10)
    max_opt_out_rate: float = Field(default=0.10, gt=0, le=0.20)
    min_sample: int = Field(default=20, ge=5, le=200)


class MandateCreateIn(BaseModel):
    campaign_id: str
    name: str = Field(default="Mandat d'automatisation", min_length=2, max_length=120)
    daily_cap: int = Field(ge=1, le=100)
    total_cap: int = Field(ge=1, le=100)
    days: int = Field(ge=1, le=90)  # the expiry date: a mandate does not last forever
    window_start_hour: int = Field(default=8, ge=0, le=23)
    window_end_hour: int = Field(default=18, ge=1, le=24)
    min_delay_seconds: int = Field(default=60, ge=30, le=3600)
    search_every_hours: int = Field(default=24, ge=6, le=168)
    ai_budget: int = Field(default=0, ge=0, le=1000)  # AI generations allowed: 0 = none, the template is controlled
    stop_rules: MandateStopRulesIn = Field(default_factory=MandateStopRulesIn)


class MandateActivateIn(BaseModel):
    acknowledgements: List[str] = Field(default_factory=list, max_length=8)  # the four codes of the authorisation


class MandateOut(BaseModel):
    data: Dict[str, Any]
