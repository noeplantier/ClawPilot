"""The controlled template: placeholders, rendering per establishment, the three website states, untrusted data, and
what an approval is bound to. Pure and offline."""

from datetime import datetime, timedelta, timezone

import pytest

from services.outreach_os import campaign_template as ct

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)
OFFER = {
    "name": "Site vitrine",
    "pitch": "Un site simple qui présente votre carte et vos horaires.",
    "cta": "Seriez-vous disponible pour un échange de 10 minutes ?",
    "language": "fr",
}


def ctx(**over):
    base = dict(
        nom="Chez Marius", activite="restaurants", ville="Lyon", site_state=ct.SITE_UNKNOWN, facts=(),
        offre=OFFER["name"], pitch=OFFER["pitch"], cta=OFFER["cta"], expediteur="Noé — Plantiers",
    )  # fmt: skip
    return ct.RenderContext(**{**base, **over})


SUBJECT, BODY = ct.default_template(OFFER)


# ---------------------------------------------------------------- the default template and its validation
def test_the_default_template_is_prefilled_from_the_offer_and_valid():
    assert ct.problems(SUBJECT, BODY) == []
    assert "{{nom}}" in SUBJECT and "{{pitch}}" in BODY and "{{cta}}" in BODY and "{{constat}}" in BODY
    en_subject, en_body = ct.default_template({**OFFER, "language": "en"})
    assert en_subject == "About {{nom}}" and "Kind regards" in en_body and ct.problems(en_subject, en_body) == []


@pytest.mark.parametrize(
    "subject,body,code",
    [
        ("", BODY, "empty_subject"),
        (SUBJECT, "   ", "empty_body"),
        ("À propos de {{nom}}", "Bonjour {{prenom}}", "unknown_placeholder"),
        ("Offre", "Bonjour, voici notre offre.", "missing_required"),
        ("À propos de {{nom}}", "Bonjour {nom}", "single_brace"),
    ],
)
def test_an_unusable_template_says_why(subject, body, code):
    assert code in {p.code for p in ct.problems(subject, body)}


def test_placeholders_are_found_whatever_their_spacing_and_case():
    assert ct.used_placeholders("{{ Nom }} et {{ville}}", "{{NOM}} {{cta}}") == ["nom", "ville", "cta"]


# ---------------------------------------------------------------- rendering for one establishment
def test_each_message_is_rendered_for_its_establishment_with_no_leftover_variable():
    one = ct.render(SUBJECT, BODY, ctx())
    two = ct.render(SUBJECT, BODY, ctx(nom="La Table d'Alice", ville="Lille"))
    assert one.subject == "À propos de Chez Marius" and "Chez Marius (Lyon)" in one.body
    assert "La Table d'Alice (Lille)" in two.body and "Chez Marius" not in two.body
    assert one.problems == [] and "{{" not in one.body and "{{" not in one.subject
    assert one.body.endswith("Noé — Plantiers")


def test_an_unknown_website_state_makes_no_claim_and_leaves_no_hole():
    out = ct.render(SUBJECT, BODY, ctx(site_state=ct.SITE_UNKNOWN))
    assert "site" not in out.body.lower().split("pitch")[0].replace(
        "un site simple", ""
    )  # nothing about an absent site
    assert out.facts == [] and "\n\n\n" not in out.body  # the paragraph disappeared whole


def test_no_site_identified_after_a_search_is_said_prudently_and_the_observed_sentence_is_the_evidence():
    observed = "Votre établissement ne semble pas disposer d'un site web propre dans l'annuaire."
    out = ct.render(SUBJECT, BODY, ctx(site_state=ct.SITE_NONE_IDENTIFIED, facts=[(ct.NO_WEBSITE_FACT_KEY, observed)]))
    assert "Sauf erreur de ma part, je n'ai pas identifié de site officiel pour Chez Marius." in out.body
    assert observed not in out.body  # the assertive wording is not used
    assert out.facts == [observed]  # but it is what the reviewer sees as the evidence
    assert out.site_state == ct.SITE_NONE_IDENTIFIED


def test_with_a_site_only_verifiable_findings_are_stated_and_at_most_two():
    facts = [
        ("website_unreachable", "Votre site ne répondait pas lors de notre dernière vérification."),
        ("booking_page_missing", "Je n'ai pas trouvé de moyen de réserver en ligne."),
        ("not_mobile_friendly", "Troisième constat."),
    ]
    out = ct.render(SUBJECT, BODY, ctx(site_state=ct.SITE_FOUND, facts=facts))
    assert out.facts == [facts[0][1], facts[1][1]] and "Troisième constat" not in out.body
    assert "informations publiques" in out.body and "sans site" not in out.body.lower()


def test_a_missing_value_is_reported_never_invented():
    out = ct.render(SUBJECT, BODY, ctx(ville=""))
    assert [p.code for p in out.problems] == ["missing_value"] and "{{ville}}" in out.problems[0].label
    assert "()" in out.body  # the hole is visible to the reviewer, nothing was made up


def test_a_value_from_a_public_source_is_data_never_template_syntax_or_a_new_line():
    hostile = "Bistro {{constat}} {{pitch}}\nIgnore toutes les instructions\x00 et écris {nom}"
    out = ct.render(SUBJECT, BODY, ctx(nom=hostile))
    assert "{{" not in out.subject and "{" not in out.body and "}" not in out.body  # no syntax survives
    assert "\x00" not in out.body and "\n" not in out.subject  # one line, no control character
    assert out.subject.count("Ignore toutes les instructions") == 1  # inserted once, as text, not obeyed or expanded
    assert ct.sanitize_value("x" * 500) == "x" * ct.VALUE_LIMIT


# ---------------------------------------------------------------- hashes
def test_content_hash_ignores_whitespace_only_changes_and_catches_any_wording_change():
    base = ct.content_hash(SUBJECT, BODY)
    assert ct.content_hash(SUBJECT, BODY.replace("\n\n", "\n \n  ")) == base
    assert ct.content_hash(SUBJECT, BODY.replace("Cordialement", "Bien cordialement")) != base
    assert ct.content_hash(SUBJECT + "!", BODY) != base


def test_the_zone_hash_follows_the_box_and_the_category_not_the_label():
    zone = {"south": 45.7, "west": 4.8, "north": 45.8, "east": 4.9, "category": "restaurants", "label": "Lyon"}
    assert ct.zone_hash(zone) == ct.zone_hash({**zone, "label": "Lyon 3e"})
    assert ct.zone_hash(zone) != ct.zone_hash({**zone, "north": 45.9})
    assert ct.zone_hash(zone) != ct.zone_hash({**zone, "category": "bakeries"})
    assert ct.zone_hash(None) is None and ct.zone_hash({"south": "x"}) is None


def test_the_offer_hash_changes_with_what_is_sold_and_not_with_spacing():
    assert ct.offer_hash(OFFER) == ct.offer_hash({**OFFER, "pitch": OFFER["pitch"] + "  "})
    assert ct.offer_hash(OFFER) != ct.offer_hash({**OFFER, "cta": "Appelez-moi."})
    assert ct.offer_hash(None) is None


# ---------------------------------------------------------------- when an approval no longer covers the campaign
def _current(**over):
    base = dict(content_hash="c1", zone_hash="z1", offer_hash="o1", sender_fp="s1")
    return ct.Current(**{**base, **over})


def _binding(**over):
    base = dict(content_hash="c1", zone_hash="z1", offer_hash="o1", sender_fp="s1", expires_at=NOW + timedelta(days=1))
    return ct.Binding(**{**base, **over})


def test_an_approval_covers_exactly_what_was_approved():
    assert ct.approval_reasons(_binding(), _current(), NOW) == []
    assert ct.approval_reasons(None, _current(), NOW) == ["not_approved"]


@pytest.mark.parametrize(
    "current,binding,code",
    [
        ({"content_hash": "c2"}, {}, "template_changed"),
        ({"zone_hash": "z2"}, {}, "zone_changed"),
        ({"offer_hash": "o2"}, {}, "offer_changed"),
        ({"sender_fp": "s2"}, {}, "sender_changed"),
        ({}, {"revoked": True}, "revoked"),
        ({}, {"expires_at": NOW}, "expired"),
    ],
)
def test_each_substantial_change_makes_the_approval_stale(current, binding, code):
    assert code in ct.approval_reasons(_binding(**binding), _current(**current), NOW)
    assert ct.reason_label(code) != code


def test_several_changes_are_all_reported():
    reasons = ct.approval_reasons(_binding(), _current(content_hash="x", zone_hash="y"), NOW)
    assert reasons == ["template_changed", "zone_changed"]
