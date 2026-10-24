from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

OUTREACH_LIVE_ALLOWLIST = {"founder@plantiers.com"}

class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str

@router.post("/email/send")
async def send_email(request: EmailRequest):
    if request.to not in OUTREACH_LIVE_ALLOWLIST:
        raise HTTPException(status_code=403, detail="Recipient not in allowlist.")
    
    # Simulate sending email
    return {"status": "Email sent successfully to " + request.to}