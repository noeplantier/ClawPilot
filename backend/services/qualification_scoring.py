"""Deterministic scores for data-backed lead qualification; never calls a provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

PRIORITY_HIGH = 75
PRIORITY_MEDIUM = 50


@dataclass(frozen=True)
class QualificationScore:
    website_quality: int
    digital_maturity: int
    fit_score: int
    priority: str


def _items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def priority_for(score: int) -> str:
    if score >= PRIORITY_HIGH:
        return "high"
    if score >= PRIORITY_MEDIUM:
        return "medium"
    return "low"


def score_qualification(
    *,
    website_url: str,
    cache_data: dict[str, Any],
    company_name: str | None,
    vertical: str | None,
    city: str | None,
    country: str | None,
    email: str | None,
    phone: str | None,
    title: str | None,
) -> QualificationScore:
    """Score only persisted enrichment and CRM fields using fixed, explainable weights.

    Fit is a data-backed qualification proxy, not an ICP or conversion prediction.
    """
    emails = _items(cache_data.get("emails"))
    phones = _items(cache_data.get("phones"))
    socials = _items(cache_data.get("socials"))
    technologies = _items(cache_data.get("technologies"))
    try:
        secure = urlparse(website_url).scheme.lower() == "https"
    except ValueError:
        secure = False
    has_form = cache_data.get("has_form") is True

    website_quality = min(
        100,
        30 + 10 * secure + 20 * bool(email or emails) + 15 * bool(phone or phones) + 15 * has_form + 10 * bool(socials),
    )
    digital_maturity = min(
        100,
        20 + 10 * secure + 25 * has_form + min(30, 15 * len(set(technologies))) + min(15, 5 * len(set(socials))),
    )

    profile_completeness = (
        20 * bool(company_name and company_name.strip())
        + 15 * bool(vertical and vertical.strip())
        + 10 * bool(city and city.strip())
        + 10 * bool(country and country.strip())
        + 20 * bool(email or emails)
        + 15 * bool(phone or phones)
        + 10 * bool(title and title.strip())
    )
    fit_score = (50 * profile_completeness + 30 * website_quality + 20 * digital_maturity + 50) // 100
    return QualificationScore(
        website_quality=website_quality,
        digital_maturity=digital_maturity,
        fit_score=fit_score,
        priority=priority_for(fit_score),
    )
