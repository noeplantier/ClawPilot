"""AI message generation route."""
from fastapi import APIRouter, Depends
from models import AIGenerateIn, AIGenerateOut
from deps import get_current_user
from services.ai_svc import generate_message

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate", response_model=AIGenerateOut)
async def generate(payload: AIGenerateIn, user: dict = Depends(get_current_user)):
    out = await generate_message(
        recipient_name=payload.recipient_name,
        product=payload.product,
        language=payload.language,
        tone=payload.tone,
        channel=payload.channel,
        goal=payload.goal,
        company=payload.company,
    )
    return out
