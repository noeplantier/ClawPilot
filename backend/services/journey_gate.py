"""The send-time check of a campaign that has a zone: is it still approved, for what it is now?

`campaign_launch._send_one` calls `check` for every message of such a campaign, at the moment it would leave. A
message is never sent on the strength of an approval that no longer matches the template, the zone, the offer or the
sender, that was revoked or expired, or whose caps are spent. A refusal that a person can fix by approving again stops
the message (it is planned again by the new approval); a daily cap only makes it wait.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign, CampaignApproval
from repositories import draft_job_repo, journey_repo, send_policy_repo
from services import send_gate
from services.outreach_os import ai_draft, campaign_template
from services.outreach_os.drafts import SenderIdentity


def sender_fp() -> Optional[str]:
    sender = SenderIdentity.from_env()
    if sender is None:
        return None
    return campaign_template.sender_fingerprint(sender.name, sender.company, sender.postal_address, sender.reply_to)


async def current_offer_hash(session: AsyncSession, account_id: uuid.UUID) -> Optional[str]:
    return campaign_template.offer_hash(ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id)))


def binding_of(approval: Optional[CampaignApproval]) -> Optional[campaign_template.Binding]:
    if approval is None:
        return None
    return campaign_template.Binding(
        content_hash=approval.content_hash,
        zone_hash=approval.zone_hash,
        offer_hash=approval.offer_hash,
        sender_fp=approval.sender_fp,
        expires_at=approval.expires_at,
        revoked=approval.revoked_at is not None,
    )


async def current_of(session: AsyncSession, campaign: Campaign) -> campaign_template.Current:
    template = await journey_repo.latest_template(session, campaign.account_id, campaign.id)
    return campaign_template.Current(
        content_hash=template.content_hash if template else "",
        zone_hash=campaign_template.zone_hash(campaign.zone),
        offer_hash=await current_offer_hash(session, campaign.account_id),
        sender_fp=sender_fp(),
    )


async def reasons(
    session: AsyncSession, campaign: Campaign, now: datetime
) -> tuple[Optional[CampaignApproval], list[str]]:
    """(the approval in force, why it no longer covers the campaign). No approval = ["not_approved"]."""
    approval = await journey_repo.latest_approval(session, campaign.account_id, campaign.id)
    return approval, campaign_template.approval_reasons(binding_of(approval), await current_of(session, campaign), now)


async def check(
    session: AsyncSession,
    campaign: Campaign,
    now: datetime,
    draft_template: Optional[str] = None,
    dispatch_id: Optional[uuid.UUID] = None,
) -> Optional[tuple[str, Optional[datetime]]]:
    """None when the message may go on, else (reason code, retry time or None). Reasons are the keys of
    `campaign_plan.SEND_REFUSALS`. `draft_template` is the template version the draft was written from: a draft of an
    older version never leaves under a newer approval."""
    approval, why = await reasons(session, campaign, now)
    if why or approval is None:
        return (why[0] if why else "not_approved"), None
    if draft_template is not None and draft_template != f"journey-{approval.template_version}":
        return "template_changed", None
    sent_total = await journey_repo.sent_count(session, campaign.account_id, campaign.id, exclude=dispatch_id)
    if sent_total >= approval.total_cap:
        return "cap_total", None
    policy = await send_policy_repo.get_policy(session, campaign.account_id, "email")
    day_start, day_end = send_gate.day_bounds(now, policy.account_default_timezone)
    today = await journey_repo.sent_count(session, campaign.account_id, campaign.id, day_start, exclude=dispatch_id)
    if today >= approval.daily_cap:
        return "cap_daily", day_end + timedelta(seconds=1)
    return None
