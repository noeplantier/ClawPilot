"""Import every model module so `Base.metadata` is fully populated for Alembic
autogenerate and for `Base.metadata.create_all()` in tests."""

from db.models.account import Account, User
from db.models.agent import Agent
from db.models.campaign import Campaign, CampaignLead, CampaignStep, SendPolicy
from db.models.consent import ConsentCurrent, ConsentRecord
from db.models.lead import Contact, Lead, LeadScore, LeadSource
from db.models.outreach import EmailSend, OutreachEvent, WhatsappSend
from db.models.taxonomy import LeadTag, Segment, Tag
from db.models.webhook import WebhookEvent
from db.models.workspace import AuditLog, Note, Task

__all__ = [
    "Account",
    "User",
    "Agent",
    "Campaign",
    "CampaignLead",
    "CampaignStep",
    "SendPolicy",
    "ConsentCurrent",
    "ConsentRecord",
    "Contact",
    "Lead",
    "LeadScore",
    "LeadSource",
    "EmailSend",
    "OutreachEvent",
    "WhatsappSend",
    "LeadTag",
    "Segment",
    "Tag",
    "WebhookEvent",
    "AuditLog",
    "Note",
    "Task",
]
