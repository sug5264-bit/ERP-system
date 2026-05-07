from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.tenants.models import Tenant, UserTenant
from app.modules.tenants.schemas import TenantCreate, TenantOut, UserTenantAssign

router = APIRouter(
    prefix="/api/tenants",
    tags=["tenants"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db)):
    return db.query(Tenant).order_by(Tenant.code).all()


@router.post(
    "",
    response_model=TenantOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    if db.query(Tenant).filter(Tenant.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    t = Tenant(**payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/me", response_model=list[TenantOut])
def my_tenants(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Tenants this user has access to. Admins see all tenants."""
    if user.role.value == "admin":
        return db.query(Tenant).order_by(Tenant.code).all()
    rows = (
        db.query(Tenant)
        .join(UserTenant, UserTenant.tenant_id == Tenant.id)
        .filter(UserTenant.user_id == user.id)
        .order_by(Tenant.code)
        .all()
    )
    return rows


@router.post(
    "/assign",
    dependencies=[Depends(require_role("admin"))],
)
def assign_user(payload: UserTenantAssign, db: Session = Depends(get_db)):
    existing = (
        db.query(UserTenant)
        .filter(
            UserTenant.user_id == payload.user_id,
            UserTenant.tenant_id == payload.tenant_id,
        )
        .first()
    )
    if existing:
        existing.is_default = payload.is_default
    else:
        db.add(UserTenant(**payload.model_dump()))
    db.commit()
    return {"ok": True}


def get_current_tenant_id(request: Request) -> int | None:
    """Resolve active tenant from `X-Tenant-ID` header. Returns None if not set."""
    raw = request.headers.get("X-Tenant-ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
