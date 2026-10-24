from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

SUPPRESSION_LIST = set()

class UnsubscribeRequest(BaseModel):
    email: str

@router.post("/email/unsubscribe")
async def unsubscribe(request: UnsubscribeRequest):
    SUPPRESSION_LIST.add(request.email)
    return {"status": f"{request.email} has been unsubscribed."}