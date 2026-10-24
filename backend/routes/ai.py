"""AI message generation route."""

import asyncio
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user
from models import AIGenerateIn, AIGenerateOut
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


class VariantsOut(BaseModel):
    variants: List[AIGenerateOut]


@router.post("/generate", response_model=AIGenerateOut)
async def generate(payload: AIGenerateIn, user: dict = Depends(get_current_user)):
    _spend(user)
    try:
        return await generate_message(
            recipient_name=payload.recipient_name,
            product=payload.product,
            language=payload.language,
            tone=payload.tone,
            channel=payload.channel,
            goal=payload.goal,
            company=payload.company,
        )
    except AIUnavailable as exc:
        raise _unavailable(exc)


@router.post("/generate/variants", response_model=VariantsOut)
async def generate_variants(payload: AIGenerateIn, user: dict = Depends(get_current_user)):
    """Generate 3 tone variants in parallel: professional, friendly, urgent."""
    tones = ["professional", "friendly", "urgent"]
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
        )
        for t in tones
    ]
    try:
        results = await asyncio.gather(*tasks)
    except AIUnavailable as exc:
        raise _unavailable(exc)
    return VariantsOut(variants=results)
