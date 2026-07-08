"""Weighted lead scoring — replaces the legacy `/leads/enrich` random bump.

Every factor is a plain, explainable rule (no ML) on purpose: each contributes
a human-readable reason alongside its point value, and the whole breakdown is
stored in `lead_scores.reason` (one row per factor) so a user can see exactly
why a lead is ranked where it is. Weights are intentionally simple defaults —
the natural extension point is making them per-account configurable through
the Phase 4 automation-rules engine rather than hand-tuning per business here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Seniority signal from the lead's job title — first matching keyword wins,
# checked from most to least senior so "VP of Engineering" doesn't match "Engineering".
SENIORITY_KEYWORDS: list[tuple[str, int, str]] = [
    ("founder", 25, "Founder-level title"),
    ("ceo", 25, "C-level title"),
    ("owner", 25, "Business owner title"),
    ("cto", 22, "C-level title"),
    ("cfo", 22, "C-level title"),
    ("coo", 22, "C-level title"),
    ("chief", 22, "C-level title"),
    ("vp", 18, "VP-level title"),
    ("vice president", 18, "VP-level title"),
    ("head of", 15, "Head-of title"),
    ("director", 15, "Director-level title"),
    ("manager", 8, "Manager-level title"),
    ("lead", 6, "Team-lead title"),
]
DEFAULT_SENIORITY_SCORE = 3

# Example ICP (Ideal Customer Profile) countries — a starting default, not a
# hard business rule; tune freely per account once scoring config lands.
TARGET_COUNTRIES = {"US", "GB", "CA", "AU", "DE", "FR", "NL", "SE", "SG", "AE"}
COUNTRY_SCORE_MATCH = 15
COUNTRY_SCORE_OTHER = 5

# Tags act as the sector/offer-fit proxy until leads carry a dedicated field.
TARGET_TAGS = {"saas", "b2b", "fintech", "enterprise", "smb"}
TAG_SCORE_PER_MATCH = 6
TAG_SCORE_MAX = 18

SOURCE_KIND_SCORE: dict[str, int] = {
    "referral": 20,
    "inbound": 20,
    "api": 10,
    "csv_import": 8,
    "enrichment": 5,
    "manual": 5,
    "scraper": 3,
}
DEFAULT_SOURCE_SCORE = 5

ENGAGEMENT_POINTS = {"replied": 20, "clicked": 8, "opened": 5}
ENGAGEMENT_CAP = 30

INACTIVITY_DECAY_DAYS = 30
INACTIVITY_DECAY_POINTS = -10

MIN_SCORE = 0
MAX_SCORE = 100


@dataclass
class LeadSignals:
    """Everything the scorer needs, gathered by repositories/lead_repo.py so
    this module stays a pure function with no DB access of its own."""

    title: str | None = None
    country: str | None = None
    tags: list[str] = field(default_factory=list)
    source_kind: str | None = None
    event_counts: dict[str, int] = field(default_factory=dict)  # e.g. {"replied": 1, "opened": 3}
    days_since_last_activity: int | None = None


@dataclass
class ScoreFactor:
    reason: str
    delta: int


@dataclass
class ScoringResult:
    score: int
    factors: list[ScoreFactor]


def _score_seniority(title: str | None) -> ScoreFactor:
    if title:
        lowered = title.lower()
        for keyword, points, reason in SENIORITY_KEYWORDS:
            if keyword in lowered:
                return ScoreFactor(reason=f"{reason} ('{title}')", delta=points)
    return ScoreFactor(reason="No seniority signal in title", delta=DEFAULT_SENIORITY_SCORE)


def _score_country(country: str | None) -> ScoreFactor:
    if country and country.upper() in TARGET_COUNTRIES:
        return ScoreFactor(reason=f"Target country ({country})", delta=COUNTRY_SCORE_MATCH)
    return ScoreFactor(reason=f"Non-target country ({country or 'unknown'})", delta=COUNTRY_SCORE_OTHER)


def _score_tags(tags: list[str]) -> ScoreFactor:
    matches = sorted(TARGET_TAGS.intersection({t.lower() for t in tags}))
    points = min(len(matches) * TAG_SCORE_PER_MATCH, TAG_SCORE_MAX)
    if matches:
        return ScoreFactor(reason=f"Tag fit: {', '.join(matches)}", delta=points)
    return ScoreFactor(reason="No target tags", delta=0)


def _score_source(source_kind: str | None) -> ScoreFactor:
    points = SOURCE_KIND_SCORE.get(source_kind or "", DEFAULT_SOURCE_SCORE)
    return ScoreFactor(reason=f"Source intent ({source_kind or 'unknown'})", delta=points)


def _score_engagement(event_counts: dict[str, int]) -> ScoreFactor:
    raw = sum(ENGAGEMENT_POINTS.get(event_type, 0) * count for event_type, count in event_counts.items())
    points = min(raw, ENGAGEMENT_CAP)
    if raw:
        parts = [f"{count}x {event_type}" for event_type, count in event_counts.items() if count]
        return ScoreFactor(reason=f"Engagement: {', '.join(parts)}", delta=points)
    return ScoreFactor(reason="No engagement yet", delta=0)


def _score_decay(days_since_last_activity: int | None) -> ScoreFactor | None:
    if days_since_last_activity is not None and days_since_last_activity >= INACTIVITY_DECAY_DAYS:
        return ScoreFactor(
            reason=f"Inactive {days_since_last_activity}d — decay applied", delta=INACTIVITY_DECAY_POINTS
        )
    return None


def compute_score(signals: LeadSignals) -> ScoringResult:
    factors = [
        _score_seniority(signals.title),
        _score_country(signals.country),
        _score_tags(signals.tags),
        _score_source(signals.source_kind),
        _score_engagement(signals.event_counts),
    ]
    decay = _score_decay(signals.days_since_last_activity)
    if decay:
        factors.append(decay)

    total = sum(f.delta for f in factors)
    return ScoringResult(score=max(MIN_SCORE, min(MAX_SCORE, total)), factors=factors)
