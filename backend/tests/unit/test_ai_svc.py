"""The AI composer through an OpenAI-compatible provider, replayed offline: no socket, no key ever returned.

What is pinned here: the provider is chosen on purpose (no default), the status says what will really happen, the
request carries only the fields meant for the message (never an e-mail or a phone), and every refusal says what to do
without repeating the key.
"""

import asyncio
import copy
import json
import secrets
import socket

import pytest
import requests

from routes import ai as ai_route
from services import ai_svc
from services.rate_limit import AttemptLimiter

KEY = "k-" + secrets.token_hex(10)  # runtime-built, not a credential


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("network access in a unit test")

    monkeypatch.setattr(socket, "create_connection", refuse)


def configure(monkeypatch, provider="groq", key=KEY, **extra):
    monkeypatch.setenv("AI_PROVIDER", provider)
    monkeypatch.setenv("AI_API_KEY", key)
    for name, value in extra.items():
        monkeypatch.setenv(name, value)


class Reply:
    def __init__(self, status=200, body=None, headers=None, text_content=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body if body is not None else {"choices": [{"message": {"content": text_content}}]}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def answering(*replies):
    """A stand-in for requests.post that answers in order and records every call."""
    calls = []
    queue = list(replies)

    def post(url, **kwargs):
        calls.append({"url": url, **copy.deepcopy(kwargs)})  # the code may change its payload afterwards
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    post.calls = calls
    return post


def write(**kwargs):
    base = {"recipient_name": "Chez Marcel", "product": "OutreachOS", "company": "Marcel SARL"}
    return asyncio.run(ai_svc.generate_message(**{**base, **kwargs}))


GOOD = json.dumps({"subject": "Une idée pour Chez Marcel", "body": "Bonjour,\n\nVoici une idée."})


# ------------------------------------------------------------------------------------------------------- status
@pytest.mark.parametrize(
    "env,reason",
    [
        ({}, "AI_PROVIDER is not set"),
        ({"AI_PROVIDER": "groq"}, "AI_API_KEY is not set"),
        ({"AI_PROVIDER": "skynet", "AI_API_KEY": KEY}, "not one of"),
        ({"AI_PROVIDER": "custom", "AI_API_KEY": KEY}, "AI_BASE_URL is not set"),
        ({"AI_PROVIDER": "custom", "AI_API_KEY": KEY, "AI_BASE_URL": "https://llm.example/v1"}, "AI_MODEL is not set"),
        (
            {"AI_PROVIDER": "custom", "AI_API_KEY": KEY, "AI_BASE_URL": "http://llm.example/v1", "AI_MODEL": "m"},
            "must start with https://",
        ),
    ],
)
def test_the_composer_is_off_and_says_why_until_a_provider_and_a_key_are_set(monkeypatch, env, reason):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    state = ai_svc.status()
    assert state["active"] is False and state["mode"] == "off" and reason in state["reason"]
    assert ai_svc.config() is None


def test_each_provider_has_its_own_address_and_default_model(monkeypatch):
    seen = {}
    for provider in ("groq", "gemini", "mistral"):
        configure(monkeypatch, provider)
        state = ai_svc.status()
        seen[provider] = (state["host"], state["model"])
        assert state["active"] is True and state["mode"] == "live" and state["reason"] is None
    assert seen["groq"][0] == "api.groq.com"
    assert seen["gemini"][0] == "generativelanguage.googleapis.com"
    assert seen["mistral"][0] == "api.mistral.ai"
    assert len({model for _, model in seen.values()}) == 3


def test_a_model_and_an_address_can_be_overridden_and_a_local_server_may_use_http(monkeypatch):
    configure(monkeypatch, "groq", AI_MODEL="llama-3.1-8b-instant")
    assert ai_svc.status()["model"] == "llama-3.1-8b-instant"
    configure(monkeypatch, "custom", AI_BASE_URL="http://localhost:11434/v1/", AI_MODEL="llama3")
    cfg = ai_svc.config()
    assert cfg is not None and cfg.base_url == "http://localhost:11434/v1" and cfg.host == "localhost"


def test_the_status_never_exposes_the_key(monkeypatch):
    configure(monkeypatch)
    assert KEY not in json.dumps(ai_svc.status())
    assert ai_svc.status()["key_configured"] is True


# ---------------------------------------------------------------------------------------------------- the request
def test_nothing_is_called_and_nothing_is_invented_when_the_composer_is_off():
    with pytest.raises(ai_svc.AIUnavailable) as refused:
        write()
    assert refused.value.code == "ai_not_configured" and "AI_PROVIDER is not set" in refused.value.message


def test_the_request_goes_to_the_provider_with_the_key_and_only_the_fields_of_the_message(monkeypatch):
    configure(monkeypatch)
    post = answering(Reply(text_content=GOOD))
    monkeypatch.setattr(requests, "post", post)
    out = write(language="fr", goal="réserver un appel", channel="email")
    (call,) = post.calls
    assert call["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["allow_redirects"] is False and call["timeout"] == ai_svc.TIMEOUT
    payload = call["json"]
    assert payload["model"] == "llama-3.3-70b-versatile" and payload["response_format"] == {"type": "json_object"}
    sent = json.dumps(payload["messages"], ensure_ascii=False)
    assert "Chez Marcel" in sent and "Marcel SARL" in sent and "OutreachOS" in sent and "réserver un appel" in sent
    assert "never invent a fact" in payload["messages"][0]["content"]
    assert out == {"subject": "Une idée pour Chez Marcel", "body": "Bonjour,\n\nVoici une idée.", "language": "fr"}


def test_a_lead_s_e_mail_and_phone_cannot_reach_the_provider():
    messages = ai_svc.build_messages("Chez Marcel", "OutreachOS", "fr", "professional", "email", None, "Marcel SARL")
    assert "@" not in json.dumps(messages) and "+33" not in json.dumps(messages)
    assert "not given" not in messages[1]["content"]  # the company was given
    unknown = ai_svc.build_messages("Chez Marcel", "OutreachOS", "fr", "professional", "email", None, None)
    assert "Company: not given" in unknown[1]["content"]  # an unknown stays unknown: never filled in


def test_whatsapp_has_no_subject(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(requests, "post", answering(Reply(text_content=json.dumps({"subject": "x", "body": "Salut"}))))
    assert write(channel="whatsapp")["subject"] is None


@pytest.mark.parametrize(
    "raw,subject,body",
    [
        (GOOD, "Une idée pour Chez Marcel", "Bonjour,\n\nVoici une idée."),
        (f"```json\n{GOOD}\n```", "Une idée pour Chez Marcel", "Bonjour,\n\nVoici une idée."),
        (f"Voici : {GOOD} Bonne journée", "Une idée pour Chez Marcel", "Bonjour,\n\nVoici une idée."),
        ('{"subject": null, "body": "Juste le corps"}', None, "Juste le corps"),
        ("Pas de JSON du tout", None, "Pas de JSON du tout"),
        ('{"subject": "S", "body": ""}', None, '{"subject": "S", "body": ""}'),
    ],
)
def test_the_answer_is_read_whatever_the_model_wraps_it_in(raw, subject, body):
    assert ai_svc.parse_answer(raw) == {"subject": subject, "body": body}


def test_a_provider_without_json_mode_is_asked_again_in_plain_mode_once(monkeypatch):
    configure(monkeypatch)
    post = answering(Reply(status=400), Reply(text_content=GOOD))
    monkeypatch.setattr(requests, "post", post)
    assert write()["body"].startswith("Bonjour")
    assert "response_format" in post.calls[0]["json"] and "response_format" not in post.calls[1]["json"]


# ----------------------------------------------------------------------------------------------------- refusals
@pytest.mark.parametrize(
    "reply,code,words",
    [
        (Reply(status=401), "ai_failed", "AI_API_KEY"),
        (Reply(status=403), "ai_failed", "AI_API_KEY"),
        (Reply(status=404), "ai_failed", "AI_MODEL"),
        (Reply(status=429, headers={"Retry-After": "7"}), "ai_rate_limited", "7 s"),
        (Reply(status=429), "ai_rate_limited", "in a moment"),
        (Reply(status=500), "ai_failed", "HTTP 500"),
        (Reply(status=301), "ai_failed", "HTTP 301"),
        (Reply(body=ValueError("not json")), "ai_failed", "format"),
        (Reply(body={"choices": []}), "ai_failed", "format"),
        (Reply(text_content="   "), "ai_failed", "empty"),
    ],
)
def test_every_refusal_says_what_happened_and_never_repeats_the_key(monkeypatch, reply, code, words):
    configure(monkeypatch)
    monkeypatch.setattr(requests, "post", answering(reply))
    with pytest.raises(ai_svc.AIUnavailable) as refused:
        write()
    assert refused.value.code == code and words in refused.value.message and KEY not in refused.value.message


@pytest.mark.parametrize(
    "error,words", [(requests.Timeout(KEY), "in time"), (requests.ConnectionError(KEY), "could not be reached")]
)
def test_a_provider_that_is_slow_or_down_is_reported_without_the_error_text(monkeypatch, error, words):
    configure(monkeypatch)
    monkeypatch.setattr(requests, "post", answering(error))
    with pytest.raises(ai_svc.AIUnavailable) as refused:
        write()
    assert words in refused.value.message and KEY not in refused.value.message


# ----------------------------------------------------------------------------------------------- the route
def test_the_route_maps_each_refusal_to_its_status():
    assert ai_route._unavailable(ai_svc.AIUnavailable("ai_not_configured", "m")).status_code == 503
    assert ai_route._unavailable(ai_svc.AIUnavailable("ai_rate_limited", "m")).status_code == 429
    assert ai_route._unavailable(ai_svc.AIUnavailable("ai_failed", "m")).status_code == 502


def test_an_organisation_cannot_use_more_than_its_minute_of_model_calls(monkeypatch):
    monkeypatch.setattr(ai_route, "_limiter", AttemptLimiter(3, 60.0))
    user = {"org_id": "00000000-0000-4000-8000-000000000001"}
    ai_route._spend(user)
    ai_route._spend(user, 2)  # the three tones of a variants request count as three calls
    with pytest.raises(ai_route.HTTPException) as refused:
        ai_route._spend(user)
    assert refused.value.status_code == 429 and refused.value.detail["code"] == "ai_rate_limited"
    assert int(refused.value.headers["Retry-After"]) >= 1
    other = {"org_id": "00000000-0000-4000-8000-000000000002"}
    ai_route._spend(other)  # another organisation has its own allowance
