"""Deduplication of candidates by shared match keys (own domain, phone, name + city)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from services.outreach_os.normalize import (
    is_third_party_profile,
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
)
from services.outreach_os.types import Candidate, RawListing


def _slug(value: str | None) -> str:
    return normalize_name(value or "").replace(" ", "-")


def build_candidate(listing: RawListing) -> Candidate:
    domain = normalize_domain(listing.website)
    own_domain = None if is_third_party_profile(domain) else domain
    phone = normalize_phone(listing.phone)
    keys: list[str] = []
    if own_domain:
        keys.append(f"domain:{own_domain}")
    if phone:
        keys.append(f"phone:{phone}")
    name_key = normalize_name(listing.name)
    if name_key and listing.city:
        keys.append(f"namecity:{name_key.replace(' ', '-')}|{_slug(listing.city)}")
    return Candidate(
        listing=listing,
        name_key=name_key,
        domain=own_domain,
        phone=phone,
        email=normalize_email(listing.email),
        match_keys=keys,
    )


def _freshness(listing: RawListing) -> date:
    return listing.last_updated or date.min


def _merge(primary: Candidate, other: Candidate) -> Candidate:
    """Keep the freshest listing as primary; fill its blanks from the other. Both stay in `merged_from`."""
    first, second = (primary, other) if _freshness(primary.listing) >= _freshness(other.listing) else (other, primary)
    filled = replace(
        first.listing,
        **{
            name: getattr(second.listing, name)
            for name in ("category", "address", "postcode", "city", "phone", "email", "website", "hours", "description")
            if getattr(first.listing, name) in (None, "")
        },
    )
    merged = build_candidate(filled)
    merged.merged_from = [*first.merged_from, *second.merged_from, second.listing]
    merged.match_keys = sorted(set(first.match_keys) | set(second.match_keys) | set(merged.match_keys))
    return merged


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Merge candidates sharing at least one match key, transitively (A~B and B~C ⇒ one entity).

    Output order is the order of first appearance of each entity, so runs are deterministic.
    """
    parent = list(range(len(candidates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for i, cand in enumerate(candidates):
        for key in cand.match_keys:
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i

    clusters: dict[int, list[int]] = {}
    for i in range(len(candidates)):
        clusters.setdefault(find(i), []).append(i)

    merged: list[Candidate] = []
    for members in sorted(clusters.values(), key=lambda m: m[0]):
        entity = candidates[members[0]]
        for i in members[1:]:
            entity = _merge(entity, candidates[i])
        merged.append(entity)
    return merged
