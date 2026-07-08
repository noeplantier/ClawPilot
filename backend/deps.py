"""Shared dependencies: DB clients (Mongo legacy + Postgres) and JWT auth.

`db` (Mongo) stays until every route listed in the migration plan is cut over
(plan doc, section "Séquence de migration") — leads/campaigns/messages/webhooks/
analytics/agents/settings still read/write it. `get_current_user` itself is
already Postgres-backed: new accounts/users are created there, and their UUIDs
flow through unchanged as the `org_id` scoping key for the not-yet-migrated
Mongo collections.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from repositories import account_repo

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "1440"))

_client = AsyncIOMotorClient(MONGO_URL)
db = _client[DB_NAME]

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return pwd_ctx.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(pw, hashed)
    except Exception:
        return False


def create_access_token(user_id: str, org_id: str, email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await account_repo.get_user_by_id(session, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # dict shape preserved exactly as the legacy Mongo document (minus password_hash)
    # so every existing route/test reading user["org_id"] etc. keeps working unchanged.
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "org_id": str(user.account_id),
        "role": user.role,
        "created_at": user.created_at,
    }


def require_roles(*roles: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker
