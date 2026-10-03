"""Auth routes: register, login, me — Postgres-backed (accounts/users tables)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import create_access_token, get_current_user, hash_password, verify_password
from models import LoginIn, Organization, RegisterIn, TokenOut, User
from repositories import account_repo
from services import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user(user) -> User:
    return User(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        org_id=str(user.account_id),
        role=user.role,
        created_at=user.created_at,
    )


def _to_org(account) -> Organization:
    return Organization(id=str(account.id), name=account.name, plan=account.plan, created_at=account.created_at)


@router.post("/register", response_model=TokenOut)
async def register(payload: RegisterIn, session: AsyncSession = Depends(get_db_session)):
    wait = rate_limit.registrations.retry_after("register")
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many sign-ups, try again later", headers={"Retry-After": str(wait)}
        )
    rate_limit.registrations.record("register")
    existing = await account_repo.get_user_by_email(session, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    account, user = await account_repo.create_account_with_owner(
        session,
        org_name=payload.organization_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )

    # No demo data here: a real account starts empty. Demo data lives in scripts/seed_demo.py.

    token = create_access_token(str(user.id), str(account.id), user.email, user.role)
    return TokenOut(access_token=token, user=_to_user(user), organization=_to_org(account))


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_db_session)):
    key = payload.email.strip().lower()
    wait = rate_limit.login_failures.retry_after(key)
    if wait:  # checked before the password: a blocked address learns nothing about whether a guess was right
        raise HTTPException(
            status_code=429, detail="Too many failed attempts, try again later", headers={"Retry-After": str(wait)}
        )
    user = await account_repo.get_user_by_email(session, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        rate_limit.login_failures.record(key)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    rate_limit.login_failures.reset(key)

    account = await account_repo.get_account(session, str(user.account_id))
    if not account:
        raise HTTPException(status_code=404, detail="Organization not found")

    token = create_access_token(str(user.id), str(account.id), user.email, user.role)
    return TokenOut(access_token=token, user=_to_user(user), organization=_to_org(account))


@router.get("/me")
async def me(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    account = await account_repo.get_account(session, user["org_id"])
    return {"user": user, "organization": _to_org(account) if account else None}
