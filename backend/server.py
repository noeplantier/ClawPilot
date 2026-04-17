"""OpenClaw SaaS — FastAPI entry."""
import logging
import os
from pathlib import Path

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from routes.auth import router as auth_router
from routes.leads import router as leads_router
from routes.campaigns import router as campaigns_router
from routes.agents import router as agents_router
from routes.messages import router as messages_router
from routes.ai import router as ai_router
from routes.analytics import router as analytics_router
from routes.settings import router as settings_router
from routes.webhooks import router as webhooks_router
from services import scheduler

app = FastAPI(title="OpenClaw API", version="1.0.0")


@app.on_event("startup")
async def _startup():
    scheduler.start()


@app.on_event("shutdown")
async def _shutdown():
    scheduler.stop()


api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "openclaw", "status": "ok"}


@api_router.get("/health")
async def health():
    return {"status": "healthy"}


api_router.include_router(auth_router)
api_router.include_router(leads_router)
api_router.include_router(campaigns_router)
api_router.include_router(agents_router)
api_router.include_router(messages_router)
api_router.include_router(ai_router)
api_router.include_router(analytics_router)
api_router.include_router(settings_router)
api_router.include_router(webhooks_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("openclaw")
