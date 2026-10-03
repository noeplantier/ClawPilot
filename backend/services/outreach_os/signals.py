"""Verifiable digital-need signals, each with an explicit three-state outcome and its evidence.

DETECTED     — the observation was made and says what the signal describes.
NOT_DETECTED — the observation was made and says the opposite.
UNKNOWN      — the observation could not be made (nothing fetched, no date, not applicable).

UNKNOWN never counts for or against a prospect. Evidence strings state exactly what was looked at and
what the limits are, so a human reviewer can judge them.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Protocol

from services.outreach_os.normalize import is_third_party_profile, normalize_domain
from services.outreach_os.types import RawListing, SignalResult, SignalState, SiteSnapshot

NO_WEBSITE = "no_website"
WEBSITE_UNREACHABLE = "website_unreachable"
BOOKING_PAGE_MISSING = "booking_page_missing"
NOT_MOBILE_FRIENDLY = "not_mobile_friendly"
PUBLIC_CONTACT_PRESENT = "public_contact_present"
STALE_LISTING = "stale_listing"
INCOMPLETE_LISTING = "incomplete_listing"

SIGNAL_LABELS: dict[str, str] = {
    NO_WEBSITE: "No own website listed",
    WEBSITE_UNREACHABLE: "Website did not respond correctly",
    BOOKING_PAGE_MISSING: "No online booking detected on the homepage",
    NOT_MOBILE_FRIENDLY: "Homepage does not declare a mobile viewport",
    PUBLIC_CONTACT_PRESENT: "Public contact details available",
    STALE_LISTING: "Listing not updated recently",
    INCOMPLETE_LISTING: "Listing is missing key information",
}
ALL_SIGNALS = tuple(SIGNAL_LABELS)

BOOKING_MARKERS = ("reserv", "réserv", "book", "thefork", "lafourchette", "zenchef", "opentable", "resy", "calendly")
_VIEWPORT_RE = re.compile(r"<meta[^>]+name=[\"']viewport[\"'][^>]*content=[\"']([^\"']*)[\"']", re.IGNORECASE)
INCOMPLETE_THRESHOLD = 2


class MobileAnalyzer(Protocol):
    def is_mobile_friendly(self, html: str) -> bool | None:
        """True/False when a verdict can be given, None when it cannot."""
        ...


class ViewportMobileAnalyzer:
    """Local heuristic: a page without `<meta name="viewport" content="width=device-width…">` is flagged.

    It does not render the page, so the verdict is a heuristic, and the evidence says so.
    """

    def is_mobile_friendly(self, html: str) -> bool | None:
        match = _VIEWPORT_RE.search(html)
        return bool(match and "width=device-width" in match.group(1).replace(" ", "").lower())


def _own_website(listing: RawListing) -> tuple[str | None, str | None]:
    """Return (own domain, third-party host). At most one is set."""
    domain = normalize_domain(listing.website)
    if not domain:
        return None, None
    return (None, domain) if is_third_party_profile(domain) else (domain, None)


def _no_website(listing: RawListing, trust_absence: bool = True) -> SignalResult:
    own, third = _own_website(listing)
    if own:
        return SignalResult(NO_WEBSITE, SignalState.NOT_DETECTED, f"Website listed in {listing.source_name}: {own}")
    if third:
        return SignalResult(
            NO_WEBSITE, SignalState.DETECTED, f"Only a third-party page is listed ({third}); no own website"
        )
    if not trust_absence:
        return SignalResult(
            NO_WEBSITE,
            SignalState.UNKNOWN,
            f"No website in {listing.source_name}; an empty cell in a supplied list is not evidence that none exists",
        )
    return SignalResult(NO_WEBSITE, SignalState.DETECTED, f"No website listed in {listing.source_name}")


def _unreachable(listing: RawListing, snap: SiteSnapshot | None) -> SignalResult:
    if not _own_website(listing)[0]:
        return SignalResult(WEBSITE_UNREACHABLE, SignalState.UNKNOWN, "Not applicable: no own website listed")
    if snap is None:
        return SignalResult(WEBSITE_UNREACHABLE, SignalState.UNKNOWN, "Website was not checked")
    if snap.status is None or snap.status >= 400:
        reason = snap.error or f"HTTP {snap.status}"
        return SignalResult(WEBSITE_UNREACHABLE, SignalState.DETECTED, f"Homepage request failed: {reason}")
    return SignalResult(WEBSITE_UNREACHABLE, SignalState.NOT_DETECTED, f"Homepage answered HTTP {snap.status}")


def _has_html(snap: SiteSnapshot | None) -> bool:
    return bool(snap and snap.status is not None and snap.status < 400 and snap.html)


def _booking(snap: SiteSnapshot | None) -> SignalResult:
    if not snap or not _has_html(snap):
        return SignalResult(BOOKING_PAGE_MISSING, SignalState.UNKNOWN, "Homepage HTML not available")
    assert snap.html is not None
    lowered = snap.html.lower()
    found = next((m for m in BOOKING_MARKERS if m in lowered), None)
    if found:
        return SignalResult(BOOKING_PAGE_MISSING, SignalState.NOT_DETECTED, f'Booking marker "{found}" found')
    return SignalResult(
        BOOKING_PAGE_MISSING,
        SignalState.DETECTED,
        "No booking link or keyword found on the homepage (other pages were not checked)",
    )


def _mobile(snap: SiteSnapshot | None, analyzer: MobileAnalyzer) -> SignalResult:
    if not snap or not _has_html(snap):
        return SignalResult(NOT_MOBILE_FRIENDLY, SignalState.UNKNOWN, "Homepage HTML not available")
    assert snap.html is not None
    verdict = analyzer.is_mobile_friendly(snap.html)
    if verdict is None:
        return SignalResult(NOT_MOBILE_FRIENDLY, SignalState.UNKNOWN, "Analyzer could not give a verdict")
    if verdict:
        return SignalResult(NOT_MOBILE_FRIENDLY, SignalState.NOT_DETECTED, "Mobile viewport declared (heuristic)")
    return SignalResult(
        NOT_MOBILE_FRIENDLY,
        SignalState.DETECTED,
        "No <meta viewport width=device-width> on the homepage (heuristic, the page was not rendered)",
    )


def _contact(listing: RawListing) -> SignalResult:
    present = [label for label, value in (("phone", listing.phone), ("email", listing.email)) if value]
    if present:
        return SignalResult(
            PUBLIC_CONTACT_PRESENT,
            SignalState.DETECTED,
            f"Public {' and '.join(present)} published in {listing.source_name}",
        )
    return SignalResult(
        PUBLIC_CONTACT_PRESENT, SignalState.NOT_DETECTED, f"No phone or e-mail in {listing.source_name}"
    )


def _stale(listing: RawListing, now: date, stale_days: int) -> SignalResult:
    if listing.last_updated is None:
        return SignalResult(STALE_LISTING, SignalState.UNKNOWN, "The source gives no last-updated date")
    age = (now - listing.last_updated).days
    if age > stale_days:
        return SignalResult(
            STALE_LISTING,
            SignalState.DETECTED,
            f"Listing last updated {listing.last_updated.isoformat()} ({age} days ago, threshold {stale_days})",
        )
    return SignalResult(
        STALE_LISTING, SignalState.NOT_DETECTED, f"Listing updated {listing.last_updated.isoformat()} ({age} days ago)"
    )


def _incomplete(listing: RawListing, trust_absence: bool = True) -> SignalResult:
    checks = {
        "phone": listing.phone,
        "address": listing.address,
        "opening hours": listing.hours,
        "description": listing.description,
        "website or e-mail": listing.website or listing.email,
    }
    missing = [name for name, value in checks.items() if not value]
    if len(missing) >= INCOMPLETE_THRESHOLD and not trust_absence:
        return SignalResult(
            INCOMPLETE_LISTING,
            SignalState.UNKNOWN,
            f"Columns empty in {listing.source_name}: {', '.join(missing)} (a supplied list may simply not carry them)",
        )
    if len(missing) >= INCOMPLETE_THRESHOLD:
        return SignalResult(
            INCOMPLETE_LISTING,
            SignalState.DETECTED,
            f"Missing in {listing.source_name}: {', '.join(missing)} (absent from this source only)",
        )
    return SignalResult(
        INCOMPLETE_LISTING,
        SignalState.NOT_DETECTED,
        f"{len(missing)} of {len(checks)} key fields missing" + (f" ({', '.join(missing)})" if missing else ""),
    )


def analyze(
    listing: RawListing,
    snapshot: SiteSnapshot | None,
    *,
    now: date,
    stale_days: int = 365,
    mobile_analyzer: MobileAnalyzer | None = None,
    trust_absence: bool = True,
) -> list[SignalResult]:
    """Run every signal for one listing. Always returns one result per signal, in `ALL_SIGNALS` order.

    `trust_absence=False` is for lists a human supplied: a missing website or column is UNKNOWN, not a finding."""
    analyzer = mobile_analyzer or ViewportMobileAnalyzer()
    results = [
        _no_website(listing, trust_absence),
        _unreachable(listing, snapshot),
        _booking(snapshot),
        _mobile(snapshot, analyzer),
        _contact(listing),
        _stale(listing, now, stale_days),
        _incomplete(listing, trust_absence),
    ]
    assert tuple(r.key for r in results) == ALL_SIGNALS
    return results
