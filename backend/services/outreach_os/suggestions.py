"""Campaign suggestions computed from the organisation's REAL leads and prospects.

Pure: no I/O, no clock, no model call. A suggestion is a group of people that share something that was actually stored
(a vertical and a city, a signal detected on their own pages, a stage), ranked by how hot its members are. The text is
built from counted facts; nothing is guessed about a person. Eligibility mirrors the send rules (`sendable_now`): a
discovery prospect only counts once a human approved it and live sending is on, so the page can say what blocks a
campaign instead of pretending.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from services.outreach_os import signals as sig

MIN_GROUP = 2
TOP_EXAMPLES = 3
MAX_SUGGESTIONS = 8
HEAT_SAMPLE = 10  # the ranking looks at the hottest members, not at the average of a long tail

# What each detected signal lets you offer: a factual angle, never a claim about the person.
ANGLES: dict[str, tuple[str, str]] = {
    sig.NO_WEBSITE: ("No own website listed", "a first website"),
    sig.WEBSITE_UNREACHABLE: ("Website did not respond correctly", "a working website"),
    sig.BOOKING_PAGE_MISSING: ("No online booking detected", "online booking"),
    sig.NOT_MOBILE_FRIENDLY: ("Homepage not declared mobile-friendly", "a mobile-friendly site"),
    sig.OUTDATED_TECHNOLOGY: ("Outdated website technology", "a site refresh"),
    sig.NO_SOCIAL_PRESENCE: ("No social network linked from the homepage", "a social presence set-up"),
    sig.STALE_LISTING: ("Listing not updated recently", "a refreshed listing"),
    sig.INCOMPLETE_LISTING: ("Listing missing key information", "a completed listing"),
}

Kind = Literal["segment", "signal", "hot", "new_leads"]


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    is_prospect: bool  # a discovery prospect (reviewed by a human) rather than a CRM lead
    review_status: Optional[str]  # pending | approved | rejected; None for a CRM lead
    vertical: Optional[str]
    city: Optional[str]
    stage: Optional[str]  # CRM stage
    heat: int
    tier: str
    has_email: bool
    has_phone: bool
    signals: frozenset[str]
    sendable_now: bool


@dataclass
class Suggestion:
    id: str
    kind: Kind
    title: str
    angle: Optional[str]
    rationale: str
    total: int
    eligible: int  # can be put in a campaign today
    pending_review: int
    hot: int
    with_email: int
    with_phone: int
    avg_heat: int
    priority: int
    examples: list[str]
    blocked_reason: Optional[str]
    member_ids: list[str] = field(default_factory=list)
    eligible_ids: list[str] = field(default_factory=list)


def _sid(kind: str, key: str) -> str:
    return hashlib.sha1(f"{kind}|{key}".encode()).hexdigest()[:12]


def _reachable(c: Candidate) -> bool:
    return c.has_email or c.has_phone


def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _build(
    kind: Kind, key: str, title: str, angle: Optional[str], members: list[Candidate], what: str, dry_run: bool
) -> Suggestion:
    ordered = sorted(members, key=lambda c: (-c.heat, c.name.casefold(), c.id))
    eligible = [c for c in ordered if c.sendable_now and _reachable(c)]
    pending = sum(1 for c in ordered if c.is_prospect and c.review_status == "pending")
    approved = sum(1 for c in ordered if c.is_prospect and c.review_status == "approved")
    hot = sum(1 for c in ordered if c.tier == "hot")
    with_email = sum(1 for c in ordered if c.has_email)
    with_phone = sum(1 for c in ordered if c.has_phone)
    sample = [c.heat for c in ordered[:HEAT_SAMPLE]]
    avg = (sum(sample) + len(sample) // 2) // len(sample)
    facts = [
        f"{_plural(len(ordered), 'person', 'people')} {what}",
        f"{hot} hot",
        f"{with_email} with a known e-mail",
        f"{with_phone} with a known phone",
    ]
    rationale = ", ".join(facts) + "."
    blocked: Optional[str] = None
    if not eligible:
        if any(c.is_prospect for c in ordered) and dry_run:
            blocked = "Live sending is off (dry-run): discovery prospects cannot join a campaign yet."
        elif pending:
            blocked = (
                f"{_plural(pending, 'prospect')} wait{'s' if pending == 1 else ''} for approval in the review queue."
            )
        elif approved and not (with_email or with_phone):
            blocked = "No one in this group has a known e-mail or phone."
        else:
            blocked = "Nobody in this group can receive a message yet."
    return Suggestion(
        id=_sid(kind, key),
        kind=kind,
        title=title,
        angle=angle,
        rationale=rationale,
        total=len(ordered),
        eligible=len(eligible),
        pending_review=pending,
        hot=hot,
        with_email=with_email,
        with_phone=with_phone,
        avg_heat=avg,
        priority=avg + min(len(ordered), 20),
        examples=[c.name for c in ordered[:TOP_EXAMPLES]],
        blocked_reason=blocked,
        member_ids=[c.id for c in ordered],
        eligible_ids=[c.id for c in eligible],
    )


def suggest(candidates: Iterable[Candidate], *, dry_run: bool) -> list[Suggestion]:
    """Up to MAX_SUGGESTIONS suggestions, the most promising first (hottest members, then size)."""
    people = [c for c in candidates if c.review_status != "rejected"]
    out: list[Suggestion] = []

    segments: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for c in people:
        if c.is_prospect and c.vertical and c.city:
            segments[(c.vertical.strip().casefold(), c.city.strip().casefold())].append(c)
    for (vertical, city), members in segments.items():
        if len(members) >= MIN_GROUP:
            label = (members[0].vertical or "").strip()
            title = f"{label[:1].upper()}{label[1:]} in {(members[0].city or '').strip()}"
            out.append(_build("segment", f"{vertical}|{city}", title, None, members, "found there", dry_run))

    for key, (label, offer) in ANGLES.items():
        members = [c for c in people if c.is_prospect and key in c.signals]
        if len(members) >= MIN_GROUP:
            out.append(
                _build(
                    "signal",
                    key,
                    label,
                    f"Offer: {offer}",
                    members,
                    f"with this signal detected on their own pages: {label.lower()}",
                    dry_run,
                )
            )

    hot = [c for c in people if c.tier == "hot" and _reachable(c)]
    if len(hot) >= MIN_GROUP:
        out.append(
            _build(
                "hot", "hot-reachable", "Your hottest reachable contacts", None, hot, "are hot and reachable", dry_run
            )
        )

    fresh = [c for c in people if not c.is_prospect and c.stage == "new" and _reachable(c)]
    if len(fresh) >= MIN_GROUP:
        out.append(
            _build(
                "new_leads",
                "new-leads",
                "New leads still waiting for a first message",
                None,
                fresh,
                "are new leads with a known contact",
                dry_run,
            )
        )

    out.sort(key=lambda s: (-s.priority, -s.hot, s.title.casefold()))
    return out[:MAX_SUGGESTIONS]
