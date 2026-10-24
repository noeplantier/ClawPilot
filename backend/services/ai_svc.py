"""AI message generation through any OpenAI-compatible provider (Groq, Gemini, Mistral, or your own endpoint).

Nothing here is canned: with no provider configured the composer refuses and says what to set (`AIUnavailable`). The
provider is chosen on purpose (`AI_PROVIDER`), because what is sent to it leaves this server: the recipient's name and
company, the offer and the goal. Never the e-mail address, the phone number or any other field of the lead.

    AI_PROVIDER  groq | gemini | mistral | custom      (no default: the choice of who receives names is yours)
    AI_API_KEY   the provider's key (never shown, never logged)
    AI_MODEL     optional: overrides the provider's default model
    AI_BASE_URL  only for `custom`: https://…/v1 (the API root that serves /chat/completions and /models)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

# provider -> (API root, default model). Models change: AI_MODEL overrides; the Settings test checks the model exists.
PROVIDERS: dict[str, tuple[Optional[str], Optional[str]]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
    "custom": (None, None),
}
TIMEOUT = (5, 40)  # connect, read (seconds)
MAX_TOKENS = 700
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class AIUnavailable(Exception):
    """The composer cannot write a real message right now. Never replaced by a canned text that pretends to be one."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AIConfig:
    provider: str
    base_url: str
    model: str
    key: str = ""

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).hostname or ""


def _read() -> tuple[Optional[AIConfig], Optional[str]]:
    """(config, None) when a provider can be called, else (None, why not): the reason is safe to show."""
    provider = os.environ.get("AI_PROVIDER", "").strip().lower()
    key = os.environ.get("AI_API_KEY", "").strip()
    if not provider:
        return None, "AI_PROVIDER is not set (groq, gemini, mistral or custom)"
    if provider not in PROVIDERS:
        return None, f"AI_PROVIDER '{provider}' is not one of: {', '.join(PROVIDERS)}"
    if not key:
        return None, "AI_API_KEY is not set"
    default_url, default_model = PROVIDERS[provider]
    base_url = (os.environ.get("AI_BASE_URL", "").strip() or default_url or "").rstrip("/")
    model = os.environ.get("AI_MODEL", "").strip() or default_model or ""
    if not base_url:
        return None, "AI_BASE_URL is not set (required with AI_PROVIDER=custom)"
    if not model:
        return None, "AI_MODEL is not set (required with AI_PROVIDER=custom)"
    parts = urlsplit(base_url)
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS):
        return None, "AI_BASE_URL must start with https:// (the key travels in every request)"
    if not parts.hostname:
        return None, "AI_BASE_URL is not a valid address"
    return AIConfig(provider, base_url, model, key), None


def config() -> Optional[AIConfig]:
    return _read()[0]


def status() -> dict[str, Any]:
    """What the AI composer will really do right now. Settings shows this instead of a hard-coded 'ACTIVE'."""
    cfg, reason = _read()
    return {
        "key_configured": bool(os.environ.get("AI_API_KEY", "").strip()),
        "provider": cfg.provider if cfg else (os.environ.get("AI_PROVIDER", "").strip().lower() or None),
        "model": cfg.model if cfg else None,
        "host": cfg.host if cfg else None,
        "active": cfg is not None,
        "mode": "live" if cfg else "off",
        "reason": reason,
    }


def _headers(cfg: AIConfig) -> dict[str, str]:
    return {"Authorization": f"Bearer {cfg.key}", "Content-Type": "application/json"}


def _post(cfg: AIConfig, payload: dict[str, Any]) -> requests.Response:
    return requests.post(
        f"{cfg.base_url}/chat/completions", headers=_headers(cfg), json=payload, timeout=TIMEOUT, allow_redirects=False
    )


def explain_http_error(status_code: int, retry_after: Optional[str] = None) -> tuple[str, str]:
    """(code, message) for a provider's HTTP answer. Only the status is used: a body can echo the request."""
    if status_code in (401, 403):
        return "ai_failed", f"The AI provider rejected the key (HTTP {status_code}). Check AI_API_KEY."
    if status_code == 404:
        return "ai_failed", "The AI provider does not know this model or address (HTTP 404). Check AI_MODEL."
    if status_code == 429:
        wait = f" Try again in {retry_after} s." if retry_after and retry_after.isdigit() else " Try again in a moment."
        return "ai_rate_limited", f"The AI provider's free limit is reached (HTTP 429).{wait}"
    return "ai_failed", f"The AI provider answered HTTP {status_code}. Nothing was generated."


def build_messages(
    recipient_name: str,
    product: str,
    language: str,
    tone: str,
    channel: str,
    goal: Optional[str],
    company: Optional[str],
) -> list[dict[str, str]]:
    """The only data that leaves this server for a message: these fields, never the lead's e-mail or phone."""
    system = (
        "You are an expert B2B outreach copywriter. Write concise, personalised messages. "
        "Use ONLY the facts given below about the recipient and their company: never invent a fact, a figure, an "
        "event or a relationship ('I saw that you…', 'congratulations on…'). "
        "If something is not given, do not mention it. "
        'Output STRICT JSON only: {"subject": string|null, "body": string}. No markdown, no code fences, no commentary.'
    )
    channel_hint = (
        "Format for EMAIL: subject (max 8 words) and body (120-160 words, 2-4 short paragraphs)."
        if channel == "email"
        else "Format for WHATSAPP: subject=null, body under 60 words, friendly, no formal signature."
    )
    user = (
        f"Recipient: {recipient_name}\n"
        f"Company: {company or 'not given'}\n"
        f"Product/Offer: {product}\n"
        f"Goal: {goal or 'book a meeting'}\n"
        f"Tone: {tone}\n"
        f"Language: {language} (write the message in this language)\n"
        f"Channel: {channel}\n"
        f"{channel_hint}\n"
        "Greet the recipient by the name given and tie the offer to the goal. End with a clear single-sentence CTA."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_answer(raw: str) -> dict[str, Optional[str]]:
    """{"subject", "body"} from the model's text: JSON (even in a fence or prose), else the text itself as the body."""
    text = (raw or "").strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and isinstance(data.get("body"), str) and data["body"].strip():
                subject = data.get("subject")
                return {
                    "subject": subject.strip() if isinstance(subject, str) and subject.strip() else None,
                    "body": data["body"].strip(),
                }
        except ValueError:
            pass
    return {"subject": None, "body": text}


def _generate_sync(cfg: AIConfig, messages: list[dict[str, str]]) -> str:
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    response = _post(cfg, payload)
    if response.status_code == 400:  # a provider or model without JSON mode: ask again in plain mode, once
        payload.pop("response_format")
        response = _post(cfg, payload)
    if response.status_code != 200:
        code, message = explain_http_error(response.status_code, response.headers.get("Retry-After"))
        raise AIUnavailable(code, message)
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AIUnavailable("ai_failed", "The AI provider answered in a format this server does not understand.")
    if not isinstance(content, str) or not content.strip():
        raise AIUnavailable("ai_failed", "The AI provider returned an empty message. Nothing was generated.")
    return content


async def generate_message(
    recipient_name: str,
    product: str,
    language: str = "en",
    tone: str = "professional",
    channel: str = "email",
    goal: str | None = None,
    company: str | None = None,
) -> dict:
    """A message from the provider, or `AIUnavailable` saying why (not configured, rejected, limit, unreachable)."""
    cfg, reason = _read()
    if cfg is None:
        raise AIUnavailable(
            "ai_not_configured",
            f"The AI composer is off: {reason}. Write the message yourself, or set it up in Settings > Integrations.",
        )
    messages = build_messages(recipient_name, product, language, tone, channel, goal, company)
    try:
        raw = await asyncio.to_thread(_generate_sync, cfg, messages)  # blocking socket: never on the event loop
    except AIUnavailable:
        raise
    except requests.Timeout:
        raise AIUnavailable("ai_failed", "The AI provider did not answer in time. Nothing was generated.")
    except requests.RequestException as exc:
        logger.warning("AI provider unreachable: %s", type(exc).__name__)
        raise AIUnavailable("ai_failed", "The AI provider could not be reached. Nothing was generated.")
    answer = parse_answer(raw)
    return {
        "subject": answer["subject"] if channel == "email" else None,
        "body": answer["body"] or "",
        "language": language,
    }
