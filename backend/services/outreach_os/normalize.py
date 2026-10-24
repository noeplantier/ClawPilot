"""Normalisation of names, phones, domains and e-mails, and match keys for deduplication."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse

# Names are compared after dropping legal forms and generic words, so "Restaurant Chez Marcel SARL"
# and "Chez Marcel" collapse to the same key.
_NAME_NOISE = {"sarl", "sas", "sasu", "eurl", "sa", "restaurant", "resto", "le", "la", "les", "l", "du", "de", "des"}

# Pages on these hosts are profiles on someone else's platform, not the business's own website.
THIRD_PARTY_HOSTS = {
    "facebook.com",
    "instagram.com",
    "tripadvisor.com",
    "tripadvisor.fr",
    "thefork.com",
    "thefork.fr",
    "google.com",
    "maps.google.com",
    "linktr.ee",
    "pagesjaunes.fr",
    "yelp.com",
}

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    folded = _strip_accents(name).lower().replace("&", " et ")
    tokens = [t for t in re.split(r"[^a-z0-9]+", folded) if t and t not in _NAME_NOISE]
    return " ".join(tokens)


def normalize_phone(raw: str | None) -> str | None:
    """Return an E.164-like number, or None when it cannot be read reliably (never guess)."""
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("+"):
        number = "+" + re.sub(r"\D", "", digits)
        return number if 8 <= len(number) - 1 <= 15 else None
    digits = re.sub(r"\D", "", digits)
    if len(digits) == 10 and digits.startswith("0"):  # French national format
        return "+33" + digits[1:]
    return None


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url.strip()
    if "//" not in candidate:
        candidate = "//" + candidate
    host = (urlparse(candidate).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host or None


def is_third_party_profile(domain: str | None) -> bool:
    if not domain:
        return False
    return any(domain == h or domain.endswith("." + h) for h in THIRD_PARTY_HOSTS)


def normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    email = raw.strip().lower()
    return email if _EMAIL_RE.match(email) else None


def identity_hash(kind: str, value: str) -> str:
    """Stable digest used by the suppression list, so opted-out identities need not be stored in clear."""
    return hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()
