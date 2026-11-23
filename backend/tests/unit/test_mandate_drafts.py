"""Tranche 2: automatic drafts from mandate Hot Leads. Offline only: no provider, network or real send."""

import asyncio
import uuid
from types import SimpleNamespace

from routes.outreach_mandates import _draft_stream
from services import ai_svc, draft_runner
from tasks import outreach_mandate_tasks as mandate_tasks


def test_precision_model_is_a_real_config_not_a_claim(monkeypatch):
    monkeypatch.delenv("AI_MODEL_PRECISION", raising=False)
    assert ai_svc.precision_model() is None
    monkeypatch.setenv("AI_MODEL_PRECISION", "  a-better-model  ")
    assert ai_svc.precision_model() == "a-better-model"


def test_only_selected_leads_can_use_the_precision_generator():
    fast, precise = object(), object()
    assert draft_runner._pick_generator(fast, precise, False) is fast
    assert draft_runner._pick_generator(fast, None, True) is fast  # no tier configured: never pretend
    assert draft_runner._pick_generator(fast, precise, True) is precise


def test_best_leads_rank_by_signals_the_discovery_engine_really_detected():
    best = (uuid.uuid4(), {"signals": [{"state": "detected"}, {"state": "detected"}]})
    second = (uuid.uuid4(), {"signals": [{"state": "detected"}, {"state": "absent"}]})
    weakest = (uuid.uuid4(), {"signals": [{"state": "absent"}]})
    assert mandate_tasks._best([weakest, second, best], 2) == [best[0], second[0]]
    assert mandate_tasks._best([], 3) == []


def test_draft_stream_counts_only_real_job_statuses():
    class Result:
        def all(self):
            return [("queued", 2), ("ready", 1), ("not_a_status", 9)]

    class Session:
        async def execute(self, statement):
            return Result()

    out = asyncio.run(_draft_stream(Session(), uuid.uuid4(), [uuid.uuid4()]))
    assert out["available"] is True
    assert out["queued"] == 2 and out["ready"] == 1
    assert out["total"] == 3  # an unknown status is never counted as a draft
    assert "not_a_status" not in out


def test_draft_stream_with_no_hot_leads_reports_not_wired_yet_zero():
    class Session:
        async def execute(self, statement):
            raise AssertionError("no query should be needed before there are Hot Leads")

    out = asyncio.run(_draft_stream(Session(), uuid.uuid4(), []))
    assert out["available"] is True and out["total"] == 0 and out["ready"] == 0


def test_draft_trigger_caps_generation_at_the_remaining_ai_budget(monkeypatch):
    account_id = uuid.uuid4()
    lead_ids = [uuid.uuid4() for _ in range(3)]
    mandate = SimpleNamespace(id=uuid.uuid4(), account_id=account_id, ai_budget=2)
    hot = [
        (lead_ids[0], {"signals": [{"state": "detected"}, {"state": "detected"}]}),
        (lead_ids[1], {"signals": [{"state": "detected"}]}),
        (lead_ids[2], {"signals": []}),
    ]
    calls = {}

    async def fake_hot(session, mandate_id, *, batch_id=None):
        return hot

    async def fake_ready(session, account_id_, ids):
        return {lead_ids[2]}  # one lead already has a ready draft -> one credit spent

    async def fake_prepare(account_id_, **kwargs):
        calls.update(kwargs)
        return {"ready": 1}

    monkeypatch.setattr(mandate_tasks, "_hot_items", fake_hot)
    monkeypatch.setattr(mandate_tasks, "_ready_leads", fake_ready)
    monkeypatch.setattr(mandate_tasks.draft_runner, "prepare", fake_prepare)
    monkeypatch.setattr(mandate_tasks.ai_svc, "precision_model", lambda: "precision-model")

    result = asyncio.run(mandate_tasks._draft_hot_leads(None, mandate, uuid.uuid4()))

    assert result["started"] is True
    assert result["budget_remaining"] == 1
    assert calls["only"] == [lead_ids[0]]  # never more leads than remaining credits
    assert calls["budget"] == 1
    assert calls["precision_ids"] == {lead_ids[0]}  # best of the leads we will actually draft
    assert result["precision_configured"] is True
    assert result["precision_leads"] == 1


def test_draft_trigger_stops_when_budget_is_spent_or_zero(monkeypatch):
    mandate = SimpleNamespace(id=uuid.uuid4(), account_id=uuid.uuid4(), ai_budget=1)
    hot = [(uuid.uuid4(), {"signals": []})]

    async def fake_hot(session, mandate_id, *, batch_id=None):
        return hot

    async def fake_ready(session, account_id, ids):
        return {hot[0][0]}

    monkeypatch.setattr(mandate_tasks, "_hot_items", fake_hot)
    monkeypatch.setattr(mandate_tasks, "_ready_leads", fake_ready)
    assert asyncio.run(mandate_tasks._draft_hot_leads(None, mandate, uuid.uuid4()))["reason"] == "ai_budget_reached"

    mandate.ai_budget = 0
    assert asyncio.run(mandate_tasks._draft_hot_leads(None, mandate, uuid.uuid4()))["reason"] == "no_ai_budget"
