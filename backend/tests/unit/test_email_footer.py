"""The mandatory footer of legacy e-mails: pure text, nothing invented."""

from services.outreach_os import email_footer

ARGS = {"name": "Noé Plantier", "company": "Plantiers", "postal_address": "1 rue X, 75001 Paris"}
URL = "https://api.example.test/api/unsubscribe/abc.def"


def _footer(source=None):
    return email_footer.render_footer(**ARGS, source=source, unsubscribe_url=URL)


def test_the_footer_carries_identity_origin_and_unsubscribe_link():
    footer = _footer("Registre public")
    assert footer.splitlines()[:3] == ["—", "Noé Plantier — Plantiers", "1 rue X, 75001 Paris"]
    assert "Origine de vos données : Registre public." in footer
    assert footer.splitlines()[-1] == f"Pour ne plus recevoir de messages de notre part : {URL}"


def test_the_footer_prints_the_configured_coordinates_and_only_those():
    full = email_footer.render_footer(
        **ARGS, source="X", unsubscribe_url=URL, reply_to="founder@plantiers.com", whatsapp="+33 6 66 16 77 88"
    )
    assert "founder@plantiers.com · WhatsApp : +33 6 66 16 77 88" in full.splitlines()
    only_mail = email_footer.render_footer(**ARGS, source="X", unsubscribe_url=URL, reply_to="founder@plantiers.com")
    assert "founder@plantiers.com" in only_mail.splitlines() and "WhatsApp" not in only_mail  # nothing invented
    assert "·" not in _footer("X") and "@" not in _footer("X")  # no coordinates configured: no empty line


def test_the_message_and_the_footer_split_back_apart_at_the_last_separator():
    footer = email_footer.render_footer(**ARGS, source="X", unsubscribe_url=URL, reply_to="a@b.example")
    message = "Bonjour,\n\n—\nune ligne qui ressemble à un séparateur\n\nCordialement"
    assert email_footer.split_footer(f"{message}\n\n{footer}") == (message, footer)
    assert email_footer.split_footer("Sans pied") == ("Sans pied", "")


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
