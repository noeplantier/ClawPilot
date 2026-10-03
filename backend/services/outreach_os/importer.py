"""Import of a prospect list supplied by a human (CSV or JSON): parse, validate, bound. Pure, no I/O.

A list is only data the operator says they may use: the legal basis and the origin are recorded with the batch, and
what the list does not say is never turned into a claim (see `signals.analyze(trust_absence=False)`).
The parser never invents a value: an unreadable cell is a row error, not a guess.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone
from services.outreach_os.types import RawListing, SiteSnapshot

MAX_ROWS = 1000
MAX_BYTES = 2_000_000
MAX_FIELD = 500
MAX_LONG_FIELD = 2000
FORMATS = ("csv", "json")

# Accepted column names (lower case, accents and spaces folded to `_`) → the field they fill.
ALIASES: dict[str, str] = {
    "name": "name", "nom": "name", "company": "name", "entreprise": "name", "societe": "name", "raison_sociale": "name",
    "email": "email", "e_mail": "email", "mail": "email", "courriel": "email",
    "phone": "phone", "telephone": "phone", "tel": "phone",
    "website": "website", "site": "website", "site_web": "website", "url": "website",
    "address": "address", "adresse": "address",
    "postcode": "postcode", "code_postal": "postcode", "zip": "postcode",
    "city": "city", "ville": "city",
    "category": "category", "categorie": "category", "secteur": "category",
    "description": "description",
    "hours": "hours", "horaires": "hours",
    "last_updated": "last_updated", "date_maj": "last_updated", "updated": "last_updated",
    "external_id": "external_id", "id": "external_id",
    "source_url": "source_url",
}  # fmt: skip
LONG_FIELDS = {"description", "hours"}
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:(?!\d)", re.IGNORECASE)  # `javascript:`, `data:`, `ftp://`; not `host:8080`
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class RowError:
    row: int  # 1-based data row (the header is row 0)
    message: str


@dataclass
class ParsedImport:
    listings: list[RawListing] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)
    rows_total: int = 0
    content_sha256: str = ""


class ImportRejected(ValueError):
    """The whole file is unusable (too large, unreadable, wrong shape): nothing is imported."""


def _fold(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower().replace("é", "e").replace("è", "e")).strip("_")


def _clean(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = _CONTROL.sub(" ", str(value)).strip()
    return text[:limit] if text else None


def _rows_from_csv(content: str) -> tuple[list[dict[str, object]], list[str]]:
    sample = content[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    if not reader.fieldnames:
        raise ImportRejected("the file has no header row")
    mapping = {name: ALIASES.get(_fold(name)) for name in reader.fieldnames if name is not None}
    if "name" not in mapping.values():
        raise ImportRejected("no name column (accepted: name, nom, company, entreprise, raison_sociale)")
    ignored = [name for name, target in mapping.items() if target is None]
    rows = []
    for raw in reader:
        rows.append({target: v for k, v in raw.items() if (target := mapping.get(k)) is not None})
    return rows, ignored


def _rows_from_json(content: str) -> tuple[list[dict[str, object]], list[str]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ImportRejected(f"invalid JSON: {exc.msg} (line {exc.lineno})") from exc
    if isinstance(data, dict):
        data = data.get("items") or data.get("prospects") or data.get("rows")
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ImportRejected("expected a JSON array of objects (or an object with an `items` array)")
    ignored: list[str] = []
    rows = []
    for item in data:
        row: dict[str, object] = {}
        for key, value in item.items():
            target = ALIASES.get(_fold(str(key)))
            if target:
                row[target] = value
            elif key not in ignored:
                ignored.append(str(key))
        rows.append(row)
    return rows, ignored


def _website(value: str | None) -> tuple[str | None, str | None]:
    """(website, error). Only http(s) or a bare domain: never `javascript:`, `data:` or similar."""
    if not value:
        return None, None
    if _SCHEME.match(value) and urlparse(value).scheme not in ("http", "https"):
        return None, "website must start with http:// or https://"
    return (
        (value, None)
        if normalize_domain(value) and "." in (normalize_domain(value) or "")
        else (None, "unreadable website")
    )


def _stable_id(row: dict[str, object]) -> str:
    key = "|".join(str(row.get(k) or "").strip().lower() for k in ("name", "email", "phone", "website", "city"))
    return "row-" + hashlib.sha256(key.encode()).hexdigest()[:12]


def parse_import(content: str, fmt: str, *, source_name: str, default_source_url: str) -> ParsedImport:
    """Parse and validate. Raises `ImportRejected` for a file that cannot be used at all; bad rows become `errors`."""
    if fmt not in FORMATS:
        raise ImportRejected(f"unknown format '{fmt}' (csv or json)")
    raw_bytes = content.encode("utf-8")
    if len(raw_bytes) > MAX_BYTES:
        raise ImportRejected(f"file too large ({len(raw_bytes)} bytes, maximum {MAX_BYTES})")
    content = content.lstrip("﻿")
    rows, ignored = _rows_from_csv(content) if fmt == "csv" else _rows_from_json(content)
    if len(rows) > MAX_ROWS:
        raise ImportRejected(f"too many rows ({len(rows)}, maximum {MAX_ROWS} per import)")

    out = ParsedImport(
        ignored_columns=ignored, rows_total=len(rows), content_sha256=hashlib.sha256(raw_bytes).hexdigest()
    )
    for number, row in enumerate(rows, start=1):
        fields = {k: _clean(v, MAX_LONG_FIELD if k in LONG_FIELDS else MAX_FIELD) for k, v in row.items()}
        name = fields.get("name")
        if not name:
            out.errors.append(RowError(number, "missing name"))
            continue
        problem = None
        email = fields.get("email")
        if email and normalize_email(email) is None:
            problem = "invalid e-mail address"
        phone = fields.get("phone")
        if phone and normalize_phone(phone) is None:
            problem = problem or "unreadable phone number (use +CC… or a French 0X… number)"
        website, website_error = _website(fields.get("website"))
        problem = problem or website_error
        updated: date | None = None
        if fields.get("last_updated"):
            try:
                updated = date.fromisoformat(str(fields["last_updated"]))
            except ValueError:
                problem = problem or "last_updated must be YYYY-MM-DD"
        if problem:
            out.errors.append(RowError(number, problem))
            continue
        out.listings.append(
            RawListing(
                external_id=fields.get("external_id") or _stable_id(row),
                name=name,
                source_name=source_name,
                source_url=fields.get("source_url") or default_source_url,
                category=fields.get("category"),
                address=fields.get("address"),
                postcode=fields.get("postcode"),
                city=fields.get("city"),
                phone=phone,
                email=email,
                website=website,
                hours=fields.get("hours"),
                description=fields.get("description"),
                last_updated=updated,
            )
        )
    return out


class ListAdapter:
    """A `SourceAdapter` over listings the operator supplied."""

    def __init__(self, name: str, license_note: str, listings: list[RawListing]) -> None:
        self.name = name
        self.license_note = license_note
        self._listings = listings

    def fetch(self) -> list[RawListing]:
        return list(self._listings)


class NoNetworkFetcher:
    """Imported lists are never enriched over the network here: sites are reported as 'not checked' (UNKNOWN)."""

    def fetch(self, url: str) -> SiteSnapshot | None:
        return None
