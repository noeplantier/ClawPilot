"""Auth routes: register, login, me."""
from fastapi import APIRouter, HTTPException, Depends

from models import RegisterIn, LoginIn, TokenOut, Organization, User
from deps import db, hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
async def register(payload: RegisterIn):
    existing = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    org = Organization(name=payload.organization_name)
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        org_id=org.id,
        role="owner",
    )

    org_doc = org.model_dump()
    org_doc["created_at"] = org_doc["created_at"].isoformat()
    user_doc = user.model_dump()
    user_doc["created_at"] = user_doc["created_at"].isoformat()
    user_doc["password_hash"] = hash_password(payload.password)

    await db.organizations.insert_one(org_doc)
    await db.users.insert_one(user_doc)

    # seed starter data
    from services.seed import seed_demo_data  # local import to avoid cycle
    await seed_demo_data(org.id)

    token = create_access_token(user.id, org.id, user.email, user.role)
    return TokenOut(access_token=token, user=user, organization=org)


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn):
    user_doc = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if not user_doc or not verify_password(payload.password, user_doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    org_doc = await db.organizations.find_one({"id": user_doc["org_id"]}, {"_id": 0})
    if not org_doc:
        raise HTTPException(status_code=404, detail="Organization not found")

    user_doc.pop("password_hash", None)
    user = User(**user_doc)
    org = Organization(**org_doc)
    token = create_access_token(user.id, org.id, user.email, user.role)
    return TokenOut(access_token=token, user=user, organization=org)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    return {"user": user, "organization": org}
