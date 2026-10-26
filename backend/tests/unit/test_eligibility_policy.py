from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql
from sqlalchemy import select

from db.models import Lead
from services.outreach_os.eligibility import evaluate, hot_expression, strict_expression


NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def qualified_evidence():
    account_id, lead_id, source_id = "account-1", "lead-1", "source-1"
    lead = {
        "id": lead_id,
        "account_id": account_id,
        "email": "contact@latable-alice.fr",
        "phone": "+33612345678",
        "website": "https://latable-alice.fr",
        "fit_score": 82,
        "qualification_scored_at": NOW - timedelta(days=1),
    }
    source = {
        "id": source_id,
        "account_id": account_id,
        "lead_id": lead_id,
        "source_name": "osm",
        "source_url": "https://openstreetmap.org/node/1",
        "license_note": "ODbL source listing",
        "fetched_at": NOW - timedelta(days=1),
        "fields": {
            "email": lead["email"],
            "website": lead["website"],
        },
    }
    signal = {
        "source_id": source_id,
    }
    page = {
        "status": "completed",
        "http_status": 200,
        "collected_at": NOW - timedelta(days=1),
        "email_verification": {lead["email"]: "syntax_valid"},
        "whatsapp_urls": ["https://wa.me/33612345678"],
    }
    return lead, [source], [signal], page


def test_complete_prospect_is_qualified_but_not_hot_without_intent():
    lead, sources, signals, page = qualified_evidence()
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is True
    assert result["status"] == "qualified"
    assert result["is_hot"] is False
    assert result["missing_fields"] == []
    assert result["policy_version"] == "strict-v1"


def test_recent_source_linked_intent_is_required_for_hot():
    lead, sources, signals, page = qualified_evidence()
    signals.append({
        "source_id": sources[0]["id"],
        "signal_key": "commercial_intent",
        "state": "detected",
        "evidence": "Inbound request asks for a quote",
        "created_at": NOW - timedelta(days=1),
    })
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is True
    assert result["is_hot"] is True


def test_name_match_alone_does_not_exclude_a_real_business():
    lead, sources, signals, page = qualified_evidence()
    lead["company"] = "La Table d'Alice"
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is True


def test_example_domain_is_excluded_without_name_based_deletion():
    lead, sources, signals, page = qualified_evidence()
    lead["email"] = "contact@business.example"
    lead["website"] = "https://business.example"
    sources[0]["fields"]["website"] = lead["website"]
    page["email_verification"] = {lead["email"]: "syntax_valid"}
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is False


def test_example_source_incomplete_channel_and_stale_evidence_fail_closed():
    lead, sources, signals, page = qualified_evidence()
    sources[0]["source_url"] = "fixture://world/example"
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is False
    assert "fresh_identifiable_source" in result["missing_fields"]

    lead, sources, signals, page = qualified_evidence()
    signals.clear()  # No sourced intent signal: a complete prospect stays qualified, not Hot.
    page["collected_at"] = NOW - timedelta(days=90)
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is False
    assert "recently_checked_official_website" in result["missing_fields"]


def test_phone_without_published_whatsapp_and_facebook_only_do_not_qualify():
    lead, sources, signals, page = qualified_evidence()
    page["whatsapp_urls"] = []
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is False
    assert "published_whatsapp_proof_and_normalized_number" in result["missing_fields"]

    lead, sources, signals, page = qualified_evidence()
    lead["website"] = "https://facebook.com/example-business"
    sources[0]["fields"]["website"] = lead["website"]
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, now=NOW)
    assert result["eligible"] is False


def test_suppressed_or_bounced_identity_is_not_eligible():
    lead, sources, signals, page = qualified_evidence()
    result = evaluate(lead, sources=sources, signals=signals, website_check=page, suppressed=True, now=NOW)
    assert result["eligible"] is False
    assert "suppressed_or_bounced" in result["reasons"]


def test_sql_policy_is_account_correlated_and_separates_hot_intent():
    strict_sql = str(select(Lead).where(strict_expression()).compile(dialect=postgresql.dialect()))
    hot_query = select(Lead).where(hot_expression()).compile(dialect=postgresql.dialect())
    hot_sql = str(hot_query)
    assert "prospect_sources.account_id = leads.account_id" in strict_sql
    assert "CAST((public_page_cache.data ->>" in strict_sql
    assert "prospect_signals.signal_key" in hot_sql
    assert "commercial_intent" in hot_query.params.values()
