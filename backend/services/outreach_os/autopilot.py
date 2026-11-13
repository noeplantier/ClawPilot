"""The autopilot: what an owner authorised the application to do by itself, and what is due now. Pure: `now` injected.

Off by default. An owner turns it on with four explicit acknowledgements; from then on, each run (scheduled, or
asked for with « Lancer maintenant ») may: search its zone again on the map (no more often than every
MIN_SEARCH_HOURS), add the places that published a phone AND an e-mail to the CRM with the same attested import as a
click on the map, approve the qualified prospects that wait for review (at most `max_approvals` per run), and prepare
their AI drafts within the credits. It never sends: sending stays the active mandate's job, inside its caps, through
every gate of the sender.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from services.outreach_os import osm

ACKNOWLEDGEMENTS = (
    "b2b_use",  # I may use the professional contacts published on the map for B2B prospecting, and honour opt-outs
    "auto_approve",  # the prospects the server qualifies are approved in my name, each decision in the audit log
    "ai_credits",  # preparing drafts spends AI credits, within the daily and session limits
    "can_stop",  # it can be stopped at any time; it never sends by itself (the mandate does, inside its caps)
)
MIN_SEARCH_HOURS = 6
MAX_APPROVALS = 200
DEFAULT_APPROVALS = 50
CATEGORIES = tuple(osm.CATEGORIES)  # the categories of a map search, one source


class Invalid(ValueError):
    def __init__(self, code: str, label: str) -> None:
        super().__init__(label)
        self.code, self.label = code, label


@dataclass(frozen=True)
class Zone:
    south: float
    west: float
    north: float
    east: float
    category: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "south": self.south,
            "west": self.west,
            "north": self.north,
            "east": self.east,
            "category": self.category,
        }


@dataclass(frozen=True)
class Settings:
    enabled: bool
    zone: Optional[Zone]
    search_every_hours: int
    max_approvals: int
    drafts: bool
    by_user_id: Optional[str]
    enabled_at: Optional[str]
    last_run_at: Optional[str]
    last_search_at: Optional[str]


OFF = Settings(False, None, 24, DEFAULT_APPROVALS, True, None, None, None, None)


def zone_of(raw: Any) -> Optional[Zone]:
    """A zone from its stored or submitted form, or None; a malformed one is refused (Invalid), never guessed."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise Invalid("bad_zone", "La zone doit être un rectangle (sud, ouest, nord, est) et une catégorie.")
    try:
        south, west, north, east = (float(raw[k]) for k in ("south", "west", "north", "east"))
    except (KeyError, TypeError, ValueError):
        raise Invalid("bad_zone", "La zone doit être un rectangle (sud, ouest, nord, est) et une catégorie.")
    category = str(raw.get("category") or "")
    if category not in CATEGORIES:
        raise Invalid("bad_category", f"Catégorie inconnue : {category or '—'}.")
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise Invalid("bad_zone", "Le rectangle de la zone est incohérent.")
    if north - south > 0.2 or east - west > 0.3:  # the limits of a map search (lib/mapSearch.js, services/osm.py)
        raise Invalid("zone_too_large", "La zone est trop grande pour une recherche : resserrez-la sur la carte.")
    return Zone(south, west, north, east, category)


def settings_of(raw: Optional[Mapping[str, Any]]) -> Settings:
    """The stored settings (accounts.autopilot), tolerant of an older or partial row: off when unreadable."""
    if not raw:
        return OFF
    try:
        zone = zone_of(raw.get("zone"))
    except Invalid:
        zone = None
    return Settings(
        enabled=bool(raw.get("enabled")),
        zone=zone,
        search_every_hours=max(MIN_SEARCH_HOURS, int(raw.get("search_every_hours") or 24)),
        max_approvals=min(MAX_APPROVALS, max(0, int(raw.get("max_approvals", DEFAULT_APPROVALS)))),
        drafts=bool(raw.get("drafts", True)),
        by_user_id=raw.get("by_user_id"),
        enabled_at=raw.get("enabled_at"),
        last_run_at=raw.get("last_run_at"),
        last_search_at=raw.get("last_search_at"),
    )


def to_row(s: Settings) -> dict[str, Any]:
    return {
        "enabled": s.enabled,
        "zone": s.zone.as_dict() if s.zone else None,
        "search_every_hours": s.search_every_hours,
        "max_approvals": s.max_approvals,
        "drafts": s.drafts,
        "by_user_id": s.by_user_id,
        "enabled_at": s.enabled_at,
        "last_run_at": s.last_run_at,
        "last_search_at": s.last_search_at,
    }


def configure(
    current: Settings,
    *,
    zone: Any,
    search_every_hours: int,
    max_approvals: int,
    drafts: bool,
    acknowledgements: list[str],
    user_id: str,
    now: datetime,
) -> Settings:
    """Turn it on (or change it): every acknowledgement by its exact code, bounded numbers. Refuses with Invalid."""
    missing = [a for a in ACKNOWLEDGEMENTS if a not in set(acknowledgements)]
    if missing:
        raise Invalid("acknowledgements_required", "Cochez les quatre confirmations : " + ", ".join(missing) + ".")
    if not MIN_SEARCH_HOURS <= int(search_every_hours) <= 24 * 30:
        raise Invalid("bad_frequency", f"Une recherche au plus toutes les {MIN_SEARCH_HOURS} h, au moins une par mois.")
    if not 0 <= int(max_approvals) <= MAX_APPROVALS:
        raise Invalid("bad_cap", f"Au plus {MAX_APPROVALS} approbations par passage.")
    return Settings(
        enabled=True,
        zone=zone_of(zone),
        search_every_hours=int(search_every_hours),
        max_approvals=int(max_approvals),
        drafts=bool(drafts),
        by_user_id=user_id,
        enabled_at=now.isoformat(),
        last_run_at=current.last_run_at,
        last_search_at=current.last_search_at,
    )


def disable(current: Settings) -> Settings:
    return Settings(
        False,
        current.zone,
        current.search_every_hours,
        current.max_approvals,
        current.drafts,
        current.by_user_id,
        None,
        current.last_run_at,
        current.last_search_at,
    )


@dataclass(frozen=True)
class Plan:
    search: bool
    approve: int  # how many qualified prospects may be approved in this run
    drafts: bool
    next_search_at: Optional[datetime]


def _parse(at: Optional[str]) -> Optional[datetime]:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at)
    except ValueError:
        return None


def plan(s: Settings, now: datetime) -> Plan:
    """What this run may do. Nothing at all when it is off."""
    if not s.enabled:
        return Plan(False, 0, False, None)
    last = _parse(s.last_search_at)
    due_at = last + timedelta(hours=s.search_every_hours) if last else None
    search = s.zone is not None and (due_at is None or now >= due_at)
    next_at = now + timedelta(hours=s.search_every_hours) if search else due_at
    return Plan(search=search, approve=s.max_approvals, drafts=s.drafts, next_search_at=next_at if s.zone else None)


def ran(s: Settings, now: datetime, *, searched: bool) -> Settings:
    return Settings(
        s.enabled,
        s.zone,
        s.search_every_hours,
        s.max_approvals,
        s.drafts,
        s.by_user_id,
        s.enabled_at,
        now.isoformat(),
        now.isoformat() if searched else s.last_search_at,
    )
