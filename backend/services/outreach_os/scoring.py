"""Explainable digital-need score: 0–100, configurable, versioned and recomputable.

points(signal) = weight if the signal is DETECTED, else 0 — UNKNOWN and NOT_DETECTED never subtract
or add. The score is the clamped sum. `coverage` tells how many of the weighted signals could actually
be observed, so a low score with low coverage reads as "not enough information", not "bad prospect".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from services.outreach_os import signals as sig
from services.outreach_os.types import SignalResult, SignalState

DEFAULT_WEIGHTS: dict[str, int] = {
    sig.NO_WEBSITE: 30,
    sig.WEBSITE_UNREACHABLE: 25,
    sig.BOOKING_PAGE_MISSING: 20,
    sig.NOT_MOBILE_FRIENDLY: 15,
    sig.PUBLIC_CONTACT_PRESENT: 10,
    sig.STALE_LISTING: 10,
    sig.INCOMPLETE_LISTING: 10,
    sig.OUTDATED_TECHNOLOGY: 10,
    sig.NO_SOCIAL_PRESENCE: 5,
}
MIN_SCORE, MAX_SCORE = 0, 100


class ScoreConfig(BaseModel):
    label: str = Field(default="default", min_length=1, max_length=80)
    weights: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    stale_days: int = Field(default=365, ge=30, le=3650)

    @field_validator("weights")
    @classmethod
    def _known_bounded(cls, weights: dict[str, int]) -> dict[str, int]:
        unknown = sorted(set(weights) - set(sig.ALL_SIGNALS))
        if unknown:
            raise ValueError(f"unknown signal(s): {', '.join(unknown)}")
        for key, value in weights.items():
            if not -100 <= value <= 100:
                raise ValueError(f"weight for {key} must be between -100 and 100")
        return weights

    def canonical(self) -> dict[str, object]:
        """The part of the config that determines the numbers (the label is cosmetic)."""
        return {"weights": {k: self.weights[k] for k in sorted(self.weights)}, "stale_days": self.stale_days}

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ScoreLine:
    signal: str
    label: str
    state: SignalState
    weight: int
    points: int
    explanation: str


@dataclass(frozen=True)
class ScoreResult:
    score: int
    coverage: float  # observed (non-UNKNOWN) share of the weighted signals, 0.0–1.0
    lines: list[ScoreLine]
    config_hash: str

    def to_breakdown(self) -> list[dict[str, object]]:
        return [
            {
                "signal": ln.signal,
                "label": ln.label,
                "state": ln.state.value,
                "weight": ln.weight,
                "points": ln.points,
                "explanation": ln.explanation,
            }
            for ln in self.lines
        ]


def compute_score(results: list[SignalResult], config: ScoreConfig) -> ScoreResult:
    by_key = {r.key: r for r in results}
    lines: list[ScoreLine] = []
    for key in sig.ALL_SIGNALS:
        weight = config.weights.get(key, 0)
        result = by_key.get(key) or SignalResult(key, SignalState.UNKNOWN, "Signal was not evaluated")
        points = weight if result.state is SignalState.DETECTED else 0
        lines.append(ScoreLine(key, sig.SIGNAL_LABELS[key], result.state, weight, points, result.evidence))
    total = sum(ln.points for ln in lines)
    weighted = [ln for ln in lines if ln.weight != 0]
    known = [ln for ln in weighted if ln.state is not SignalState.UNKNOWN]
    coverage = (len(known) / len(weighted)) if weighted else 1.0
    return ScoreResult(
        score=max(MIN_SCORE, min(MAX_SCORE, total)),
        coverage=round(coverage, 2),
        lines=lines,
        config_hash=config.config_hash,
    )
