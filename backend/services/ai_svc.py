"""AI message generation via Emergent Universal LLM key (Gemini 3 Flash)."""

import importlib.util
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")


def status() -> dict:
    """What the AI composer will really do right now. It only calls the model when a key is set AND the optional
    `emergentintegrations` package (private index, not in requirements.txt) is installed; otherwise it returns a
    fixed template. Settings shows this instead of a hard-coded 'ACTIVE'."""
    key_present = bool(EMERGENT_KEY)
    library_available = importlib.util.find_spec("emergentintegrations") is not None
    if key_present and library_available:
        mode, reason = "live", None
    elif not key_present:
        mode, reason = "template", "EMERGENT_LLM_KEY is not set"
    else:
        mode, reason = "template", "the emergentintegrations package is not installed"
    return {
        "key_configured": key_present,
        "library_available": library_available,
        "active": mode == "live",
        "mode": mode,
        "reason": reason,
    }


def _fallback(recipient_name: str, product: str, language: str, tone: str, channel: str, company: str | None) -> dict:
    subj = f"Quick idea for {company or recipient_name}"
    body = (
        f"Hi {recipient_name},\n\n"
        f"I noticed {company or 'your team'} is doing great work and thought {product} might help you move faster.\n\n"
        f"Worth a 15-min chat this week?\n\nBest,\nThe Plantiers Team"
    )
    return {"subject": subj if channel == "email" else None, "body": body, "language": language}


async def generate_message(
    recipient_name: str,
    product: str,
    language: str = "en",
    tone: str = "professional",
    channel: str = "email",
    goal: str | None = None,
    company: str | None = None,
) -> dict:
    """Generate AI message using Gemini 3 Flash via emergentintegrations."""
    if not EMERGENT_KEY:
        return _fallback(recipient_name, product, language, tone, channel, company)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        logger.warning("emergentintegrations not available: %s", e)
        return _fallback(recipient_name, product, language, tone, channel, company)

    system = (
        "You are an expert B2B outreach copywriter. "
        "Write concise, personalized, high-converting messages. "
        'Output STRICT JSON only: {"subject": string|null, "body": string}. '
        "No markdown, no code fences, no extra commentary."
    )

    channel_hint = (
        "Format for EMAIL: include subject (max 8 words) and body (120-160 words, 2-4 short paragraphs)."
        if channel == "email"
        else "Format for WHATSAPP: subject=null, body under 60 words, no formal signature, friendly."
    )

    prompt = (
        f"Recipient: {recipient_name}\n"
        f"Company: {company or 'unknown'}\n"
        f"Product/Offer: {product}\n"
        f"Goal: {goal or 'book a meeting'}\n"
        f"Tone: {tone}\n"
        f"Language: {language} (write the message in this language)\n"
        f"Channel: {channel}\n"
        f"{channel_hint}\n"
        "Add ONE specific personalization hook referencing the recipient/company. "
        "End with a clear single-sentence CTA."
    )

    try:
        chat = LlmChat(api_key=EMERGENT_KEY, session_id=f"gen-{recipient_name}", system_message=system).with_model(
            "gemini", "gemini-2.5-flash"
        )
        resp = await chat.send_message(UserMessage(text=prompt))
        raw = resp if isinstance(resp, str) else str(resp)

        # Extract JSON
        match = re.search(r"\{[\s\S]*\}", raw)
        data = json.loads(match.group(0)) if match else {"subject": None, "body": raw.strip()}
        return {
            "subject": data.get("subject"),
            "body": data.get("body", "").strip(),
            "language": language,
        }
    except Exception as e:
        logger.exception("AI generation failed, using fallback: %s", e)
        return _fallback(recipient_name, product, language, tone, channel, company)
