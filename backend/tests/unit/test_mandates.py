"""The bounded mandate: rejected payloads, draft-by-default, explicit transitions, real route registration.

Offline only: no database, no key, no provider and no transport are touched here.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from db.models.prospecting import Mandate
from routes import outreach_mandates as route
from routes.outreach_mandates import MandateIn, _aggregate_batches


def body(**over):
    base = {
        "zone": {"label": "Lyon 2e", "bbox": [45.75, 4.82, 45.77, 4.84]},
        "sector": "restaurants",
        "offer": "Plantiers – Software Engineering",
        "qualification_criteria": ["email sourcé"],
        "daily_volume": 20,
        "total_volume": 200,
        "ai_budget": 5,
        "time_windows": [{"start_hour": 9, "end_hour": 18}],
        "cadence_minutes": 1440,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "stop_rules": ["reply", "bounce"],
    }
    return {**base, **over}


def test_a_mandate_is_a_draft_until_someone_approves_it():
    # Python-side and database-side defaults both say draft; the create route also sets it explicitly.
    column = Mandate.__table__.c.status
    assert column.default is not None and "draft" in str(column.default.arg)
    assert column.server_default is not None and "draft" in str(column.server_default.arg)
    texts = [str(c.sqltext) for c in Mandate.__table__.constraints if hasattr(c, "sqltext")]
    assert any(all(status in text for status in ("draft", "active", "paused", "expired", "revoked")) for text in texts)


@pytest.mark.parametrize(
    "over",
    [
        {"zone": {"label": "Trop grand", "bbox": [45.0, 4.0, 46.0, 5.0]}},
        {"zone": {"label": "Inversé", "bbox": [45.77, 4.84, 45.75, 4.82]}},
        {"expires_at": "2030-01-01T00:00:00"},  # no timezone: never guess one
        {"expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        {"daily_volume": 300, "total_volume": 200},
        {"ai_budget": -1},
        {"cadence_minutes": 30},
        {"time_windows": [{"start_hour": 18, "end_hour": 9}]},
    ],
)
def test_the_payload_refuses_anything_unbounded_or_ambiguous(over):
    with pytest.raises(ValidationError):
        MandateIn.model_validate(body(**over))


def test_the_mandate_payload_is_accepted_within_its_limits():
    parsed = MandateIn.model_validate(body())
    assert not hasattr(parsed, "status")  # a client cannot choose the status at creation
    assert parsed.daily_volume <= parsed.total_volume and parsed.cadence_minutes >= 60


def test_only_the_documented_transitions_are_allowed():
    class Row:
        status = "draft"

    row = Row()
    route._transition(row, ("draft",), "active")
    assert row.status == "active"
    with pytest.raises(HTTPException) as refused:
        route._transition(row, ("draft",), "active")
    assert refused.value.status_code == 409


def test_live_counts_come_only_from_counters_the_engine_wrote():
    class Batch:
        def __init__(self, status, counters, reasons, error=None):
            self.status, self.counters, self.exclusion_reasons, self.error_summary = status, counters, reasons, error

    counts = _aggregate_batches(
        [
            Batch(
                "completed",
                {"entities": 12, "duplicates_merged": 3, "qualified_strict": 4, "hot": 2, "failed": 1},
                {"duplicate": 2},
            ),
            Batch("discovering", {"entities": 5, "hot": 1}, {}, "registry_fr: Timeout"),
        ]
    )
    assert counts == {
        "leads_discovered": 17,
        "duplicates_excluded": 5,  # merged listings + staged duplicates
        "leads_qualified": 4,
        "hot_leads": 3,
        "errors": 2,  # one failed provider + one batch with an error summary
        "discovery_in_progress": True,
    }
    assert _aggregate_batches([])["leads_discovered"] == 0
    assert _aggregate_batches([])["discovery_in_progress"] is False


def test_the_mandates_endpoint_is_registered_under_the_api_prefix():
    from server import app

    paths = app.openapi()["paths"]
    assert (
        "/api/outreach-mandates" in paths
        and "post" in paths["/api/outreach-mandates"]
        and "get" in paths["/api/outreach-mandates"]
    )
    for action in ("activate", "pause", "resume", "revoke"):
        assert f"/api/outreach-mandates/{{mandate_id}}/{action}" in paths
    assert "get" in paths["/api/outreach-mandates/{mandate_id}/live"]
