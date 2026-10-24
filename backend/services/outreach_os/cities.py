"""Per-city lead counts for the map's town search. Pure: no I/O, no clock.

The database groups by the city as written (`Lyon`, `lyon `, `LYON`); here the spellings that mean the same town are
merged: accents, case, hyphens, apostrophes and `St`/`Ste` for `Saint`/`Sainte` do not make another city. The figures
are counted, never estimated: a town with no lead is not in the answer (the page says so).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable, TypedDict

TIERS = ("hot", "warm", "cold")
_SAINT = {"st": "saint", "ste": "sainte"}


class CityHeat(TypedDict):
    city: str  # a capitalised spelling from the data, the most used one
    key: str  # fold(city): what the page matches on
    hot: int
    warm: int
    cold: int
    total: int


def _capitalised(name: str) -> bool:
    return name != name.upper() and name != name.lower()


def fold(name: str) -> str:
    """`Saint-Étienne`, `st etienne` and `SAINT ETIENNE` give the same key."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    words = re.split(r"[^a-z0-9]+", plain.lower())
    return " ".join(_SAINT.get(w, w) for w in words if w)


def merge(rows: Iterable[tuple[str, str, int]]) -> list[CityHeat]:
    """`rows` are (city as written, tier, number of leads). Hottest cities first, then the biggest, then by name."""
    spellings: dict[str, Counter[str]] = {}
    counts: dict[str, dict[str, int]] = {}
    for city, tier, n in rows:
        key = fold(city)
        if not key or tier not in TIERS or n <= 0:
            continue
        spellings.setdefault(key, Counter())[city.strip()] += n
        counts.setdefault(key, dict.fromkeys(TIERS, 0))[tier] += n
    out: list[CityHeat] = []
    for key, by_tier in counts.items():
        # a capitalised spelling over a shouted or lowercase one, then the most used, then alphabetical: stable whatever
        # order the database answered in
        shown = sorted(spellings[key].items(), key=lambda kv: (not _capitalised(kv[0]), -kv[1], kv[0]))[0][0]
        out.append(
            {
                "city": shown,
                "key": key,
                "hot": by_tier["hot"],
                "warm": by_tier["warm"],
                "cold": by_tier["cold"],
                "total": sum(by_tier.values()),
            }
        )
    out.sort(key=lambda c: (-c["hot"], -c["total"], c["key"]))
    return out
