"""Source adapters: where listings and homepage snapshots come from.

Only local fixtures are implemented. A network-backed adapter must stay behind the `external_sources`
feature flag and honour robots.txt and the source's terms (see docs/compliance.md) before it exists.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from services.outreach_os.types import RawListing, SiteSnapshot

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
DEMO_SOURCE_NAME = "fixture_directory"
DEMO_SOURCE_LICENSE = "Fictional data generated for demos and tests; no real business or person."


class SourceAdapter(Protocol):
    name: str
    license_note: str

    def fetch(self) -> list[RawListing]: ...


class SiteFetcher(Protocol):
    def fetch(self, url: str) -> SiteSnapshot | None:
        """Return the snapshot, or None when the URL was not checked (which is not the same as a failure)."""
        ...


class _DirectoryParser(HTMLParser):
    """Reads `<article class="listing" ...>` blocks with `<p class="phone">`-style fields."""

    FIELDS = {"name", "category", "address", "phone", "email", "hours", "description"}

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        classes = a.get("class", "").split()
        if tag == "article" and "listing" in classes:
            self._current = {"external_id": a.get("data-id", ""), "last_updated": a.get("data-updated", "")}
        elif self._current is not None:
            if tag == "a" and "website" in classes:
                self._current["website"] = a.get("href", "")
            else:
                field = next((c for c in classes if c in self.FIELDS), None)
                if field:
                    self._field = field

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._field and data.strip():
            self._current[self._field] = (self._current.get(self._field, "") + " " + data.strip()).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self._current is not None:
            self.rows.append(self._current)
            self._current = None
        self._field = None


_POSTCODE_CITY = re.compile(r"(\d{5})\s+(.+)$")


def parse_directory(html: str, *, source_name: str, source_url: str) -> list[RawListing]:
    parser = _DirectoryParser()
    parser.feed(html)
    listings: list[RawListing] = []
    for row in parser.rows:
        if not row.get("name") or not row.get("external_id"):
            continue  # unusable entry: skip rather than invent identity
        postcode = city = None
        address = row.get("address") or None
        if address and (m := _POSTCODE_CITY.search(address)):
            postcode, city = m.group(1), m.group(2).strip()
        try:
            updated = date.fromisoformat(row["last_updated"]) if row.get("last_updated") else None
        except ValueError:
            updated = None
        listings.append(
            RawListing(
                external_id=row["external_id"],
                name=row["name"],
                source_name=source_name,
                source_url=source_url,
                category=row.get("category") or None,
                address=address,
                postcode=postcode,
                city=city,
                phone=row.get("phone") or None,
                email=row.get("email") or None,
                website=row.get("website") or None,
                hours=row.get("hours") or None,
                description=row.get("description") or None,
                last_updated=updated,
            )
        )
    return listings


class FixtureDirectoryAdapter:
    """Reads a directory page saved on disk. Never touches the network."""

    name = DEMO_SOURCE_NAME
    license_note = DEMO_SOURCE_LICENSE

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or FIXTURES_ROOT) / "restaurants_demo"

    def fetch(self) -> list[RawListing]:
        html = (self.root / "directory.html").read_text(encoding="utf-8")
        return parse_directory(html, source_name=self.name, source_url="fixture://restaurants_demo/directory.html")


class FixtureSiteFetcher:
    """Serves homepage snapshots from `sites.json` + `sites/*.html`. Unknown URLs are 'not checked'."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or FIXTURES_ROOT) / "restaurants_demo"
        self._index: dict[str, dict[str, object]] = json.loads((self.root / "sites.json").read_text(encoding="utf-8"))

    def fetch(self, url: str) -> SiteSnapshot | None:
        entry = self._index.get(url)
        if entry is None:
            return None
        status = entry.get("status")
        file = entry.get("file")
        html = (self.root / "sites" / str(file)).read_text(encoding="utf-8") if file else None
        error = entry.get("error")
        return SiteSnapshot(
            url=url,
            status=status if isinstance(status, int) else None,
            html=html,
            error=str(error) if error else None,
        )
