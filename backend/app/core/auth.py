from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Role precedence: viewer < staff < manager < admin
_ROLE_ORDER = {"viewer": 0, "staff": 1, "manager": 2, "admin": 3}


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(min_role: str):
    """Dependency factory: ensure current user has at least the given role.

    Usage:
        @router.post("/x", dependencies=[Depends(require_role("manager"))])
    """
    threshold = _ROLE_ORDER[min_role]

    def _checker(user=Depends(get_current_user)):
        user_level = _ROLE_ORDER.get(user.role.value if hasattr(user.role, "value") else user.role, -1)
        if user_level < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{min_role}' or higher",
            )
        return user

    return _checker
