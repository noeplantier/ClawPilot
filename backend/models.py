"""Pydantic models for OpenClaw SaaS platform."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Literal
import uuid

from pydantic import BaseModel, Field, EmailStr, ConfigDict


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


# ------------------------ Campaigns ------------------------
CampaignStatus = Literal["draft", "running", "paused", "completed"]
Channel = Literal["email", "whatsapp"]


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
    channels: List[Channel] = Field(default_factory=lambda: ["email"])
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
    channels: List[Channel] = Field(default_factory=lambda: ["email"])
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


# ------------------------ Agents (OpenClaw) ------------------------
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


# ------------------------ Settings ------------------------
class IntegrationSettings(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_account_sid_configured: bool = False
    sendgrid_configured: bool = False


class SettingsUpdate(BaseModel):
    sendgrid_from_email: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
