"""A public contact e-mail published on a business's OWN homepage (a `mailto:` link). Pure: no I/O.

Only an address the site itself publishes as a link, on the site's own domain (or an obvious generic address of the
business), is returned: nothing is guessed from a name or a pattern, and addresses found in page text, scripts or
images are ignored. Platform-hosted pages and no-reply/technical addresses are refused.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote

from services.outreach_os.normalize import normalize_domain, normalize_email

_MAILTO = re.compile(r"""href\s*=\s*["']mailto:([^"'?#\s>]+)""", re.IGNORECASE)
_TECHNICAL = re.compile(
    r"^(no-?reply|donotreply|do-not-reply|postmaster|webmaster|abuse|privacy|dpo|noreply|mailer-daemon)@|"
    r"@(sentry|wixpress|example|domain|email)\.|@.*\.(png|jpg|gif|svg|webp)$",
    re.IGNORECASE,
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
