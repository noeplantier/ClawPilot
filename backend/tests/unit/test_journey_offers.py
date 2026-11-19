"""Which offer each recipient of a zone journey receives, as the person sees it before approving. Pure, no database:
the examples and the breakdown are computed from already rendered messages."""

from types import SimpleNamespace

from services import journey
from services.outreach_os import ai_draft

OFFERS = {
    "language": "fr",
    "default": "seo_geo",
    "offers": {
        "creation": {"name": "Création", "pitch": "Un site neuf pour présenter votre activité.", "cta": "Un appel ?"},
        "refonte_maintenance": {
            "name": "Refonte",
            "pitch": "Refondre et maintenir votre site web.",
            "cta": "On en parle ?",
        },
        "seo_geo": {
            "name": "SEO / GEO",
            "pitch": "Être trouvé sur les moteurs, les cartes et les IA.",
            "cta": "10 min ?",
        },
    },
}


def material(name, state, offers=OFFERS):
    rendered = SimpleNamespace(site_state=state, subject=name, body=name, facts=[], problems=[])
    return journey.Material(SimpleNamespace(full_name=name), rendered, None, ai_draft.offer_for(offers, state))


def test_each_case_receives_its_offer_and_unknown_receives_the_default_one():
    assert material("a", ai_draft.SITE_NONE_IDENTIFIED).offer["kind"] == "creation"
    assert material("b", ai_draft.SITE_UNREACHABLE).offer["kind"] == "refonte_maintenance"
    assert material("c", ai_draft.SITE_FOUND).offer["kind"] == "seo_geo"
    unknown = material("d", ai_draft.SITE_UNKNOWN)
    assert unknown.offer["kind"] == "seo_geo" and unknown.offer["pitch"] == OFFERS["offers"]["seo_geo"]["pitch"]


def test_a_missing_offer_falls_back_to_the_default_never_to_an_invented_one():
    two = {**OFFERS, "offers": {k: v for k, v in OFFERS["offers"].items() if k != "creation"}}
    assert material("a", ai_draft.SITE_NONE_IDENTIFIED, two).offer["kind"] == "seo_geo"


def test_the_breakdown_counts_each_offer_in_a_stable_order():
    sendable = [
        material("a", ai_draft.SITE_FOUND),
        material("b", ai_draft.SITE_NONE_IDENTIFIED),
        material("c", ai_draft.SITE_FOUND),
        material("d", ai_draft.SITE_UNREACHABLE),
    ]
    assert journey.by_offer(sendable) == [
        {"kind": "refonte_maintenance", "label": ai_draft.KIND_LABELS["refonte_maintenance"], "count": 1},
        {"kind": "creation", "label": ai_draft.KIND_LABELS["creation"], "count": 1},
        {"kind": "seo_geo", "label": ai_draft.KIND_LABELS["seo_geo"], "count": 2},
    ]
    assert journey.by_offer([]) == []


def test_the_examples_show_one_message_per_offer_before_anything_else():
    sendable = [material(f"seo{i}", ai_draft.SITE_FOUND) for i in range(5)]
    sendable += [material("creation", ai_draft.SITE_NONE_IDENTIFIED), material("refonte", ai_draft.SITE_UNREACHABLE)]
    kinds = [m.offer["kind"] for m in journey.pick_examples(sendable)]
    assert sorted(kinds) == ["creation", "refonte_maintenance", "seo_geo"]


def test_a_single_offer_account_keeps_its_offer_name_and_one_example_per_site_state():
    single = {"name": "Site vitrine", "pitch": "Un site simple qui présente votre carte.", "cta": "Un échange ?"}
    sendable = [material("a", ai_draft.SITE_FOUND, single), material("b", ai_draft.SITE_FOUND, single)]
    sendable.append(material("c", ai_draft.SITE_UNKNOWN, single))
    assert journey.by_offer(sendable) == [{"kind": "single", "label": "Site vitrine", "count": 3}]
    assert [m.lead.full_name for m in journey.pick_examples(sendable)] == ["a", "c", "b"]
