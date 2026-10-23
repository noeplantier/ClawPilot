"""A public contact e-mail published on a business's OWN site (a `mailto:` link on its homepage or its contact page).
Pure: no I/O.

Only an address the site itself publishes as a link, on the site's own domain (or an obvious generic address of the
business), is returned: nothing is guessed from a name or a pattern, and addresses found in page text, scripts or
images are ignored. Platform-hosted pages and no-reply/technical addresses are refused.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote, urljoin, urlsplit

from services.outreach_os.normalize import normalize_domain, normalize_email

_MAILTO = re.compile(r"""href\s*=\s*["']mailto:([^"'?#\s>]+)""", re.IGNORECASE)
_TECHNICAL = re.compile(
    r"^(no-?reply|donotreply|do-not-reply|postmaster|webmaster|abuse|privacy|dpo|noreply|mailer-daemon)@|"
    r"@(sentry|wixpress|example|domain|email)\.|@.*\.(png|jpg|gif|svg|webp)$",
    re.IGNORECASE,
)
_HREF = re.compile(r"""<a\s[^>]*?href\s*=\s*["']([^"'>\s]+)["']""", re.IGNORECASE)
# The last path segment of a link that leads to a contact page (English, French, Spanish, German, Italian).
_CONTACT_SEGMENT = re.compile(
    r"^(contact|contacts|contact-us|contactez-nous|nous-contacter|contact-nous"
    r"|contacto|kontakt|contatti|contattaci)(\.html?|\.php)?$"
)
MAX_HTML = 524288


def _base(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def extract_contact_email(html: str | None, site_url: str | None) -> str | None:
    domain = normalize_domain(site_url)
    if not html or not domain:
        return None
    for raw in _MAILTO.findall(html[:MAX_HTML]):
        email = normalize_email(unquote(unescape(raw)).split(",")[0])
        if not email or _TECHNICAL.search(email):
            continue
        if _base(email.split("@", 1)[1]) == _base(domain):
            return email
    return None


def find_contact_page(html: str | None, site_url: str | None) -> str | None:
    """The first link of the homepage that leads to the business's own contact page (same registrable domain), or None.

    Only http(s) links whose last path segment is a known "contact" word are followed: nothing is guessed, no other page
    of the site is read, and a link to another site is ignored.
    """
    domain = normalize_domain(site_url)
    if not html or not domain or not site_url:
        return None
    base = site_url if "//" in site_url else f"https://{site_url}"
    for raw in _HREF.findall(html[:MAX_HTML]):
        href = unescape(raw).strip()
        if href.lower().startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        target = urlsplit(urljoin(base, href))
        if target.scheme not in ("http", "https") or not target.hostname:
            continue
        if _base(normalize_domain(target.hostname) or "") != _base(domain):
            continue
        segments = [seg for seg in target.path.lower().split("/") if seg]
        if segments and _CONTACT_SEGMENT.match(segments[-1]):
            return str(target._replace(fragment="").geturl())
    return None
