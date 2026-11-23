"""Credits and outreach models over HTTP, and the refusals before any AI call. No network: AI is not configured here."""

import os

import pytest
import requests
from fastapi import HTTPException

from tests.test_map_quick_add import API, _org


def _state(h):
    r = requests.get(f"{API}/usage/credits", headers=h)
    assert r.status_code == 200
    return r.json()


def test_a_new_account_has_its_full_allowance_and_the_default_model():
    _, h, _ = _org()
    s = _state(h)
    assert s["model"] == "equilibre"
    assert [m["id"] for m in s["models"]] == ["gabarit", "rapide", "equilibre", "precision"]
    assert next(m for m in s["models"] if m["id"] == "gabarit")["credits"] == 0
    session, day = s["windows"]
    assert (session["key"], session["used"], session["resets_at"]) == ("session", 0, None)
    assert (day["key"], day["used"], day["remaining"]) == ("day", 0, day["limit"])
    assert s["settings"] == ["CREDITS_PER_DAY", "CREDITS_PER_SESSION"]  # names only
    assert s["ai_usage"]["models"] == [] and s["ai_usage"]["unattributed"] == 0  # nothing spent: nothing invented


def test_the_owner_chooses_the_model_and_an_unknown_one_is_refused():
    _, h, _ = _org()
    r = requests.put(f"{API}/usage/model", headers=h, json={"model": "rapide"})
    assert r.status_code == 200 and r.json()["model"] == "rapide"
    assert _state(h)["model"] == "rapide"
    bad = requests.put(f"{API}/usage/model", headers=h, json={"model": "gpt-9"})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "unknown_model"


def test_the_template_model_never_calls_the_ai():
    _, h, _ = _org()
    requests.put(f"{API}/usage/model", headers=h, json={"model": "gabarit"}).raise_for_status()
    r = requests.post(f"{API}/ai/generate", headers=h, json={"recipient_name": "Ana", "product": "Site vitrine"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "model_without_ai"
    assert _state(h)["windows"][1]["used"] == 0


def test_a_failed_ai_call_costs_nothing():
    _, h, _ = _org()
    r = requests.post(f"{API}/ai/generate", headers=h, json={"recipient_name": "Ana", "product": "Site vitrine"})
    assert r.status_code == 503  # AI is not configured on the test server: refused, and nothing spent
    assert all(w["used"] == 0 for w in _state(h)["windows"])


def test_a_spend_over_the_session_is_refused_before_the_provider(monkeypatch):
    from models import AIGenerateIn
    from routes import ai
    from tasks._bridge import run_async

    _, h, me = _org()
    monkeypatch.setenv("CREDITS_PER_SESSION", "1")  # the "équilibre" model costs 2: refused before any provider call
    called = []
    monkeypatch.setattr(ai, "generate_message", lambda **kw: called.append(kw))

    async def go(session):
        return await ai.generate(AIGenerateIn(recipient_name="Ana", product="Site vitrine"), user=me, session=session)

    with pytest.raises(HTTPException) as refused:
        run_async(go)
    assert refused.value.status_code == 402
    assert refused.value.detail["code"] == "credits_exhausted" and refused.value.detail["window"] == "session"
    assert "CREDITS_PER_SESSION" in refused.value.detail["message"]
    assert called == []
    assert os.environ["CREDITS_PER_SESSION"] == "1"


def test_a_successful_call_is_counted(monkeypatch):
    from models import AIGenerateIn
    from routes import ai
    from tasks._bridge import run_async

    _, h, me = _org()

    async def fake(**kw):
        assert kw["style"].id == "equilibre"
        return {"subject": "Bonjour", "body": "Un message.", "whatsapp": None, "language": "fr"}

    monkeypatch.setattr(ai, "generate_message", fake)

    async def go(session):
        out = await ai.generate(AIGenerateIn(recipient_name="Ana", product="Site vitrine"), user=me, session=session)
        await session.commit()
        return out

    assert run_async(go)["subject"] == "Bonjour"
    session_window, day = _state(h)["windows"]
    assert session_window["used"] == 2 and day["used"] == 2 and session_window["resets_at"]


def test_today_s_real_ai_usage_is_read_back_per_model_and_stays_in_its_organisation():
    import uuid
    from datetime import datetime, timedelta, timezone

    from db.models import UsageRecord
    from repositories import usage_repo
    from tasks._bridge import run_async

    _, h, me = _org()
    _, other_h, _ = _org()
    account = uuid.UUID(me["org_id"])

    async def go(session):
        meta = {"action": "draft", "model": "rapide", "ai_model": "openai/gpt-oss-20b", "ai_tokens": 250}
        await usage_repo.spend_credits(session, account, 1, meta)
        await usage_repo.spend_credits(session, account, 1, {**meta, "ai_tokens": 150})
        await usage_repo.spend_credits(session, account, 2, {"action": "composer", "model": "equilibre"})
        session.add(  # two days ago: not today's
            UsageRecord(
                account_id=account,
                kind="credits",
                quantity=1,
                meta={**meta, "ai_tokens": 9999},
                created_at=datetime.now(timezone.utc) - timedelta(days=2),
            )
        )
        await session.commit()

    run_async(go)
    usage = _state(h)["ai_usage"]
    assert usage["models"] == [{"ai_model": "openai/gpt-oss-20b", "spends": 2, "tokens": 400, "without_tokens": 0}]
    assert usage["unattributed"] == 1 and usage["since"]
    assert _state(other_h)["ai_usage"]["models"] == []  # another organisation sees nothing of it


def test_the_composer_records_its_real_usage_and_its_answer_does_not_change(monkeypatch):
    from models import AIGenerateIn
    from routes import ai
    from tasks._bridge import run_async

    _, h, me = _org()

    async def fake(**kw):
        body = {"subject": "Bonjour", "body": "Un message.", "whatsapp": None, "language": "fr"}
        return {**body, "usage": {"model": "openai/gpt-oss-120b", "tokens": 512}}

    monkeypatch.setattr(ai, "generate_message", fake)

    async def go(session):
        out = await ai.generate(AIGenerateIn(recipient_name="Ana", product="Site vitrine"), user=me, session=session)
        await session.commit()
        return out

    out = run_async(go)
    assert "usage" not in out and ai.AIGenerateOut(**out).subject == "Bonjour"  # the HTTP contract is unchanged
    usage = _state(h)["ai_usage"]
    assert usage["models"] == [{"ai_model": "openai/gpt-oss-120b", "spends": 1, "tokens": 512, "without_tokens": 0}]
    assert usage["unattributed"] == 0
