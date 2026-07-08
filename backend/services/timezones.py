"""Approximate country -> IANA timezone mapping for send-window enforcement.

Deliberately one representative zone per country, even for multi-timezone
countries (US, RU, AU, ...) — a precise per-city resolution needs geocoding
input this app doesn't collect, and an approximate window is enough value for
a first version (plan doc: "accepter l'imprécision... n'est pas un besoin
bloquant pour un MVP B2B").
"""

from __future__ import annotations

COUNTRY_TO_TIMEZONE: dict[str, str] = {
    "US": "America/New_York",
    "CA": "America/Toronto",
    "MX": "America/Mexico_City",
    "BR": "America/Sao_Paulo",
    "GB": "Europe/London",
    "FR": "Europe/Paris",
    "DE": "Europe/Berlin",
    "NL": "Europe/Amsterdam",
    "SE": "Europe/Stockholm",
    "IT": "Europe/Rome",
    "ES": "Europe/Madrid",
    "AE": "Asia/Dubai",
    "IN": "Asia/Kolkata",
    "SG": "Asia/Singapore",
    "JP": "Asia/Tokyo",
    "CN": "Asia/Shanghai",
    "AU": "Australia/Sydney",
    "NG": "Africa/Lagos",
    "ZA": "Africa/Johannesburg",
}

DEFAULT_TIMEZONE = "UTC"


def resolve_timezone(country: str | None, default: str = DEFAULT_TIMEZONE) -> str:
    if not country:
        return default
    return COUNTRY_TO_TIMEZONE.get(country.upper(), default)
