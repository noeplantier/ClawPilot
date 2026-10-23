"""Lead heat: how worth a human's time a lead is *now*, from real data only. Pure: no I/O, no clock.

heat = (score + information + 1) // 2, both 0..100, where
- `information` is the share of the 8 tracked fields that are really known (a blank, "unknown" or the import default
  "unspecified" counts as NOT known: an unknown is never filled in or treated as a value);
- `score` is the explainable score when the lead has been scored. A lead that was never scored is ranked on its
  information alone and says so (`scored: false`): "not scored" is not 0.
Tiers: hot >= 65, warm >= 40, cold below. The same arithmetic runs in SQL (`repositories/heat_sql.py`) for ordering;
integer maths on both sides keeps the two identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Optional

INFO_FIELDS = ("email", "phone", "website", "city", "company", "vertical", "country", "title")
NOT_KNOWN = {"", "unknown", "unspecified", "n/a", "none", "null", "-"}
HOT_FROM = 65
WARM_FROM = 40

Tier = Literal["hot", "warm", "cold"]


@dataclass(frozen=True)
class Heat:
    value: int
    tier: Tier
    info_pct: int
    known: tuple[str, ...]
    missing: tuple[str, ...]
    scored: bool
    score: Optional[int]


def is_known(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() not in NOT_KNOWN


def known_fields(values: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(f for f in INFO_FIELDS if is_known(values.get(f)))


def info_pct(known_count: int) -> int:
    return (known_count * 25 + 1) // 2  # k * 100 / 8, halves rounded up


def tier_of(value: int) -> Tier:
    return "hot" if value >= HOT_FROM else "warm" if value >= WARM_FROM else "cold"


def heat_of(values: Mapping[str, object], score: Optional[int]) -> Heat:
    known = known_fields(values)
    info = info_pct(len(known))
    value = info if score is None else (score + info + 1) // 2
    missing = tuple(f for f in INFO_FIELDS if f not in known)
    return Heat(value, tier_of(value), info, known, missing, score is not None, score)
