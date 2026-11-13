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
