"""ClawPilot SaaS — FastAPI entry."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from routes.agents import router as agents_router
from routes.ai import router as ai_router
from routes.analytics import router as analytics_router
from routes.auth import router as auth_router
from routes.campaigns import router as campaigns_router
from routes.leads import router as leads_router
from routes.messages import router as messages_router
from routes.notes import router as notes_router
from routes.prospects import router as prospects_router
from routes.settings import router as settings_router
from routes.tags import router as tags_router
from routes.tasks import router as tasks_router
from routes.unsubscribe import router as unsubscribe_router
from routes.webhooks import router as webhooks_router

# Delayed campaign steps run as Celery tasks in a separate worker process now
# (see celery_app.py, tasks/send_tasks.py) — nothing to start/stop here anymore.

app = FastAPI(title="ClawPilot API", version="1.0.0")

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "clawpilot", "status": "ok"}


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
api_router.include_router(notes_router)
api_router.include_router(tasks_router)
api_router.include_router(tags_router)
api_router.include_router(prospects_router)
api_router.include_router(unsubscribe_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("clawpilot")
