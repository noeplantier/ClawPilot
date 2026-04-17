"""Settings — integration status."""
import os
from fastapi import APIRouter, Depends

from deps import get_current_user
from models import IntegrationSettings
from services.sendgrid_svc import is_configured as sg_ok
from services.twilio_svc import is_configured as tw_ok

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/integrations", response_model=IntegrationSettings)
async def integrations(user: dict = Depends(get_current_user)):
    return IntegrationSettings(
        sendgrid_from_email=os.environ.get("SENDGRID_FROM_EMAIL") or None,
        twilio_whatsapp_from=os.environ.get("TWILIO_WHATSAPP_FROM") or None,
        twilio_account_sid_configured=tw_ok(),
        sendgrid_configured=sg_ok(),
    )
