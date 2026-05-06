import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import effective_role, get_current_user, hash_api_key, require_role
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.models import ApiKey, Role, User, UserModulePermission
from app.modules.auth.schemas import (
    ModulePermissionIn,
    ModulePermissionOut,
    Token,
    UserCreate,
    UserOut,
    UserUpdate,
)

MODULES_LIST = ["hr", "finance", "inventory", "sales"]

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(subject=str(user.id))
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/effective-roles")
def my_effective_roles(current_user: User = Depends(get_current_user)):
    """Return the effective role of the current user for each business module."""
    return {m: effective_role(current_user, m) for m in MODULES_LIST}


@router.get(
    "/users",
    response_model=list[UserOut],
    dependencies=[Depends(require_role("admin"))],
)
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post(
    "/users",
    response_model=UserOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        pw = data.pop("password")
        if pw:
            user.hashed_password = hash_password(pw)
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete(
    "/users/{user_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.get(
    "/users/{user_id}/permissions",
    response_model=list[ModulePermissionOut],
    dependencies=[Depends(require_role("admin"))],
)
def list_user_permissions(user_id: int, db: Session = Depends(get_db)):
    return (
        db.query(UserModulePermission)
        .filter(UserModulePermission.user_id == user_id)
        .order_by(UserModulePermission.module)
        .all()
    )


@router.put(
    "/users/{user_id}/permissions",
    response_model=list[ModulePermissionOut],
    dependencies=[Depends(require_role("admin"))],
)
def set_user_permissions(
    user_id: int,
    permissions: list[ModulePermissionIn],
    db: Session = Depends(get_db),
):
    """Replace the user's module-permission set in one call."""
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status_code=404, detail="User not found")

    db.query(UserModulePermission).filter(
        UserModulePermission.user_id == user_id
    ).delete(synchronize_session=False)

    for p in permissions:
        if p.module not in MODULES_LIST:
            raise HTTPException(status_code=400, detail=f"Unknown module: {p.module}")
        db.add(UserModulePermission(user_id=user_id, module=p.module, role=p.role))
    db.commit()

    return (
        db.query(UserModulePermission)
        .filter(UserModulePermission.user_id == user_id)
        .order_by(UserModulePermission.module)
        .all()
    )


# OAuth (Google) ---------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@router.get("/oauth/google/start")
def google_start():
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": secrets.token_urlsafe(16),
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/oauth/google/callback")
def google_callback(code: str, db: Session = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    with httpx.Client(timeout=10.0) as client:
        token_res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="OAuth token exchange failed")
        access_token = token_res.json().get("access_token")

        info = client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if info.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info")
        profile = info.json()

    email = profile.get("email")
    name = profile.get("name") or email
    if not email:
        raise HTTPException(status_code=400, detail="Email missing from Google profile")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            full_name=name,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role=Role(settings.oauth_default_role),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(subject=str(user.id))
    redirect = f"{settings.frontend_base}/login?token={jwt_token}"
    return RedirectResponse(redirect)


@router.get("/oauth/providers")
def list_providers():
    return {"google": bool(settings.google_client_id)}


# API keys --------------------------------------------------------------------


@router.get("/api-keys")
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(ApiKey)
        .filter(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "revoked": k.revoked,
            "rate_per_minute": k.rate_per_minute,
            "last_used_at": k.last_used_at,
            "created_at": k.created_at,
        }
        for k in rows
    ]


@router.post("/api-keys")
def create_api_key(
    name: str,
    rate_per_minute: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = "wg_" + secrets.token_urlsafe(32)
    record = ApiKey(
        user_id=current_user.id,
        name=name,
        key_hash=hash_api_key(raw),
        prefix=raw[:8],
        rate_per_minute=rate_per_minute,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    # Return the raw key ONCE — it cannot be retrieved later.
    return {
        "id": record.id,
        "name": record.name,
        "prefix": record.prefix,
        "key": raw,
        "warning": "Store this key now. It will not be shown again.",
    }


@router.delete("/api-keys/{key_id}")
def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    record.revoked = True
    db.commit()
    return {"ok": True}
