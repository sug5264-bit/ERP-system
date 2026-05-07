from app.core.time import utc_now
import secrets
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import effective_role, get_current_user, hash_api_key, require_role
from app.core.pagination import Page, PageParams, paginate
from app.core.config import settings
from app.core.db import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.auth.models import (
    ApiKey,
    RefreshToken,
    Role,
    User,
    UserModulePermission,
)
from app.modules.auth.schemas import (
    ModulePermissionIn,
    ModulePermissionOut,
    RefreshIn,
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


def _issue_tokens(db: Session, user: User, user_agent: str | None = None) -> Token:
    access = create_access_token(subject=str(user.id))
    jti = secrets.token_urlsafe(16)
    refresh, expire = create_refresh_token(subject=str(user.id), jti=jti)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_api_key(refresh),
            expires_at=expire.replace(tzinfo=None),
            user_agent=(user_agent or "")[:500],
        )
    )
    db.commit()
    return Token(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    from jose import JWTError

    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_api_key(payload.refresh_token))
        .first()
    )
    if not record or record.revoked:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if record.expires_at and record.expires_at < utc_now():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.id == record.user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User inactive")

    # Rotate: revoke old refresh, issue a new pair (defends against replay).
    record.revoked = True
    db.commit()
    return _issue_tokens(db, user)


@router.post("/logout")
def logout(payload: RefreshIn, db: Session = Depends(get_db)):
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_api_key(payload.refresh_token))
        .first()
    )
    if record:
        record.revoked = True
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/effective-roles")
def my_effective_roles(current_user: User = Depends(get_current_user)):
    """Return the effective role of the current user for each business module."""
    return {m: effective_role(current_user, m) for m in MODULES_LIST}


@router.get(
    "/users",
    response_model=Page[UserOut],
    dependencies=[Depends(require_role("admin"))],
)
def list_users(params: PageParams = Depends(), db: Session = Depends(get_db)):
    return paginate(db.query(User).order_by(User.id), params)


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


OAUTH_STATE_COOKIE = "wg_oauth_state"


@router.get("/oauth/google/start")
def google_start():
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    # Bind state to the user agent via a short-lived, HttpOnly cookie.
    resp.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return resp


@router.get("/oauth/google/callback")
def google_callback(
    code: str,
    state: str | None = None,
    db: Session = Depends(get_db),
    expected_state: str | None = Cookie(None, alias=OAUTH_STATE_COOKIE),
):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state (CSRF check failed)")

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
    resp = RedirectResponse(redirect)
    resp.delete_cookie(OAUTH_STATE_COOKIE)
    return resp


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
