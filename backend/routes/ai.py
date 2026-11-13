"""AI message generation route."""

import asyncio
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import AIGenerateIn, AIGenerateOut
from services import credit_gate
from services.ai_svc import AIUnavailable, generate_message
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/ai", tags=["ai"])
_limiter = AttemptLimiter(30, 60.0)  # model calls per organisation and minute: a free tier has a limit of its own
_STATUS = {"ai_not_configured": 503, "ai_rate_limited": 429}


def _unavailable(exc: AIUnavailable) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(exc.code, 502),
        detail={"code": exc.code, "message": exc.message, "retry_at": None},
    )


def _spend(user: dict, calls: int = 1) -> None:
    """Counts `calls` model calls for this organisation, or answers 429 when the minute's allowance is used up."""
    key = str(uuid.UUID(user["org_id"]))
    wait = _limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail={"code": "ai_rate_limited", "message": f"Too many AI requests: wait {wait} s.", "retry_at": None},
            headers={"Retry-After": str(wait)},
        )
    for _ in range(calls):
        _limiter.record(key)


async def _credits(session: AsyncSession, user: dict, units: int):
    """The account's model and the cost, or 402 credits_exhausted / 409 model_without_ai. Nothing is recorded yet."""
    try:
        return await credit_gate.reserve(session, uuid.UUID(user["org_id"]), units)
    except credit_gate.CreditsExhausted as exc:
        r = exc.refusal
        raise HTTPException(
            status_code=402,
            detail={
                "code": r.code,
                "message": r.message,
                "window": r.window,
                "retry_at": r.resets_at.isoformat() if r.resets_at else None,
            },
        )
    except credit_gate.ModelWithoutAI as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "model_without_ai",
                "message": f"Le modèle « {exc} » écrit sans IA : choisissez un modèle IA dans Crédits et modèles.",
                "retry_at": None,
            },
        )


class VariantsOut(BaseModel):
    variants: List[AIGenerateOut]


@router.post("/generate", response_model=AIGenerateOut)
async def generate(
    payload: AIGenerateIn, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    chosen, cost = await _credits(session, user, 1)
    _spend(user)
    try:
        out = await generate_message(
            recipient_name=payload.recipient_name,
            product=payload.product,
            language=payload.language,
            tone=payload.tone,
            channel=payload.channel,
            goal=payload.goal,
            company=payload.company,
            style=chosen,
        )
    except AIUnavailable as exc:
        raise _unavailable(exc)  # a failed call costs nothing
    await credit_gate.spent(session, uuid.UUID(user["org_id"]), chosen, cost, "composer")
    return out


@router.post("/generate/variants", response_model=VariantsOut)
async def generate_variants(
    payload: AIGenerateIn, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    """Generate 3 tone variants in parallel: professional, friendly, urgent."""
    tones = ["professional", "friendly", "urgent"]
    chosen, cost = await _credits(session, user, len(tones))
    _spend(user, len(tones))
    tasks = [
        generate_message(
            recipient_name=payload.recipient_name,
            product=payload.product,
            language=payload.language,
            tone=t,
            channel=payload.channel,
            goal=payload.goal,
            company=payload.company,
            style=chosen,
        )
        for t in tones
    ]
    try:
        results = await asyncio.gather(*tasks)
    except AIUnavailable as exc:
        raise _unavailable(exc)
    await credit_gate.spent(session, uuid.UUID(user["org_id"]), chosen, cost, "composer_variants")
    return VariantsOut(variants=results)
