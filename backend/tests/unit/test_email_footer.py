"""The mandatory footer of legacy e-mails: pure text, nothing invented."""

from services.outreach_os import email_footer

ARGS = {"name": "Noé Plantier", "company": "Plantiers", "postal_address": "1 rue X, 75001 Paris"}
URL = "https://api.example.test/api/unsubscribe/abc.def"


def _footer(source=None):
    return email_footer.render_footer(**ARGS, source=source, unsubscribe_url=URL)


def test_the_footer_carries_identity_origin_and_unsubscribe_link():
    footer = _footer("Registre public")
    assert "Noé Plantier — Plantiers — 1 rue X, 75001 Paris" in footer
    assert "Origine de vos données : Registre public." in footer
    assert URL in footer


def test_an_unrecorded_origin_is_stated_as_unrecorded_never_invented():
    footer = _footer(None)
    assert "source non renseignée" in footer
    assert "annuaire" not in footer
    assert "source non renseignée" in _footer("   ")


def test_the_footer_is_appended_once_and_the_placeholder_is_resolved():
    footer = _footer("X")
    body = email_footer.append_footer("Bonjour {{unsubscribe_url}}", footer, URL)
    assert body.startswith(f"Bonjour {URL}") and body.count(footer) == 1
    assert email_footer.append_footer(body, footer, URL) == body


def test_a_compliant_body_has_no_problems_and_a_bare_one_lists_all_three():
    full = email_footer.append_footer("Hello", _footer("X"), URL)
    assert email_footer.footer_problems(full, **ARGS, unsubscribe_url=URL) == []
    problems = email_footer.footer_problems("Hello", **ARGS, unsubscribe_url=URL)
    assert "missing sender name" in problems and "missing data-origin statement" in problems
    assert "missing working unsubscribe link" in problems
