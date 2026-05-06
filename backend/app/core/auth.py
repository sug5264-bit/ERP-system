from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Role precedence: viewer < staff < manager < admin
_ROLE_ORDER = {"viewer": 0, "staff": 1, "manager": 2, "admin": 3}


def _role_value(role) -> str:
    return role.value if hasattr(role, "value") else str(role)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from sqlalchemy.orm import selectinload

    from app.modules.auth.models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = (
        db.query(User)
        .options(selectinload(User.module_permissions))
        .filter(User.id == int(user_id))
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
