"""AI message generation route."""

import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user
from models import AIGenerateIn, AIGenerateOut
from services.ai_svc import AIUnavailable, generate_message

router = APIRouter(prefix="/ai", tags=["ai"])


def _unavailable(exc: AIUnavailable) -> HTTPException:
    return HTTPException(
        status_code=503 if exc.code == "ai_not_configured" else 502,
        detail={"code": exc.code, "message": exc.message, "retry_at": None},
    )


class VariantsOut(BaseModel):
    variants: List[AIGenerateOut]


@router.post("/generate", response_model=AIGenerateOut)
async def generate(payload: AIGenerateIn, user: dict = Depends(get_current_user)):
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
