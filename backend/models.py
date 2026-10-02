"""Pydantic models for ClawPilot SaaS platform."""

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


# ------------------------ Agents (ClawPilot) ------------------------
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
class IntegrationSettings(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_account_sid_configured: bool = False
    sendgrid_configured: bool = False


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
