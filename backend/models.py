"""Pydantic models for the Plantiers - OutreachOS platform."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

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


class AIGenerateOut(BaseModel):
    subject: Optional[str] = None
    body: str
    language: str


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
    library_available: bool = False
    active: bool = False  # True only when the model is really called
    mode: str = "template"  # "live" | "template" (fixed text, no model call)
    reason: Optional[str] = None  # why it is in template mode


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


class IntegrationSettings(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_account_sid_configured: bool = False
    sendgrid_configured: bool = False
    ai: AIStatus = Field(default_factory=AIStatus)
    outreach: OutreachStatus = Field(default_factory=OutreachStatus)
    webhooks: WebhookStatus = Field(default_factory=WebhookStatus)


class SettingsUpdate(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None


# ------------------------ OutreachOS prospects ------------------------
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


class ProspectList(BaseModel):
    items: List[ProspectSummary]
    total: int


class SignalOut(BaseModel):
    key: str
    label: str
    state: str  # unknown | detected | not_detected (enforced by a CHECK constraint)
    evidence: str
    observed_at: datetime


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


class MapSearchOut(BaseModel):
    attribution: str
    license_note: str
    truncated: bool = False  # the area held more places than the cap: zoom in to see the rest
    places: List[MapPlaceOut]
