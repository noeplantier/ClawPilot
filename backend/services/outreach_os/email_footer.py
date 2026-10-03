"""The mandatory footer of a commercial e-mail: who writes, where the data comes from, how to opt out.

Pure text, no I/O. Used by the legacy send paths (single, batch, campaign step, Celery task) so that every e-mail that
can reach a person carries the same three elements as a discovery draft. Nothing is invented: when the origin of a
contact is not recorded, the footer says so instead of naming a source.
"""

from __future__ import annotations

UNSUBSCRIBE_PLACEHOLDER = "{{unsubscribe_url}}"
SEPARATOR = "—"


def origin_line(source: str | None, company: str) -> str:
    """Where the recipient's data comes from, stated only from what is recorded."""
    if source and source.strip():
        return f"Origine de vos données : {source.strip()}."
    return (
        f"Origine de vos données : source non renseignée dans les fichiers de {company}. "
        "Répondez à ce message pour la connaître."
    )


def render_footer(*, name: str, company: str, postal_address: str, source: str | None, unsubscribe_url: str) -> str:
    return "\n".join(
        [
            SEPARATOR,
            f"{name} — {company} — {postal_address}",
            origin_line(source, company),
            f"Pour ne plus recevoir de messages de notre part : {unsubscribe_url}",
        ]
    )


def append_footer(body: str, footer: str, unsubscribe_url: str) -> str:
    """The body with the placeholder resolved and the footer appended once (a body that already carries it is kept)."""
    body = body.replace(UNSUBSCRIBE_PLACEHOLDER, unsubscribe_url)
    if footer in body:
        return body
    return f"{body.rstrip()}\n\n{footer}\n"


def footer_problems(body: str, *, name: str, company: str, postal_address: str, unsubscribe_url: str) -> list[str]:
    """What is missing from a body that is about to leave. Empty means the three mandatory elements are present."""
    problems = []
    for label, value in (("sender name", name), ("sender company", company), ("postal address", postal_address)):
        if value not in body:
            problems.append(f"missing {label}")
    if "Origine de vos données" not in body:
        problems.append("missing data-origin statement")
    if unsubscribe_url not in body:
        problems.append("missing working unsubscribe link")
    return problems
