from app.core.time import utc_now
import hashlib

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Role precedence: supplier (external, isolated) < viewer < staff < manager < admin
# `supplier` deliberately sits below viewer so role checks like require_role("viewer")
# block them from generic modules; supplier-portal endpoints accept it explicitly.
_ROLE_ORDER = {"supplier": -1, "viewer": 0, "staff": 1, "manager": 2, "admin": 3}


def _role_value(role) -> str:
    return role.value if hasattr(role, "value") else str(role)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Resolve user from either a JWT (Authorization: Bearer ...) or an API key
    (X-API-Key header). API keys are sha256-hashed in storage."""
    from datetime import datetime

    from sqlalchemy.orm import selectinload

    from app.modules.auth.models import ApiKey, User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id: int | None = None

    api_key = request.headers.get("X-API-Key")
    if api_key:
        record = (
            db.query(ApiKey)
            .filter(ApiKey.key_hash == hash_api_key(api_key), ApiKey.revoked.is_(False))
            .first()
        )
        if not record:
            raise credentials_exception
        record.last_used_at = utc_now()
        db.commit()
        user_id = record.user_id

    if user_id is None and token:
        try:
            payload = decode_token(token)
            sub = payload.get("sub")
            if sub is not None:
                user_id = int(sub)
        except JWTError:
            raise credentials_exception

    if user_id is None:
        raise credentials_exception

    user = (
        db.query(User)
        .options(selectinload(User.module_permissions))
        .filter(User.id == user_id)
        .first()
    )
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def effective_role(user, module: str | None = None) -> str:
    """Resolve the user's effective role, considering per-module overrides."""
    if module:
        for perm in getattr(user, "module_permissions", []) or []:
            if perm.module == module:
                return _role_value(perm.role)
    return _role_value(user.role)


def require_role(min_role: str):
    """Dependency factory: ensure current user has at least the given global role."""
    threshold = _ROLE_ORDER[min_role]

    def _checker(user=Depends(get_current_user)):
        if _ROLE_ORDER.get(_role_value(user.role), -1) < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{min_role}' or higher",
            )
        return user

    return _checker


def require_module_role(module: str, min_role: str):
    """Like require_role, but checks per-module permission first (with global fallback)."""
    threshold = _ROLE_ORDER[min_role]

    def _checker(user=Depends(get_current_user)):
        if _ROLE_ORDER.get(effective_role(user, module), -1) < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{min_role}' on module '{module}'",
            )
        return user

    return _checker


def is_supplier_user(user) -> bool:
    return _role_value(user.role) == "supplier"


def get_current_internal_user(user=Depends(get_current_user)):
    """Like `get_current_user`, but blocks supplier-portal accounts.

    Use this on every router whose endpoints should be invisible to suppliers.
    Supplier accounts only get into the suppliers/* and auth/* surfaces.
    """
    if is_supplier_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supplier portal users cannot access this module",
        )
    return user
