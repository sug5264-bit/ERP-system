from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import effective_role, get_current_user, require_role
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.models import User, UserModulePermission
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
