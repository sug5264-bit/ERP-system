"""자사 회사정보 — 단일 row를 upsert 패턴으로 관리.

- GET /api/company-profile: 현재 테넌트 회사정보 조회 (없으면 404)
- PUT /api/company-profile: 없으면 생성, 있으면 갱신 (admin only)
- 빈 객체 반환은 의도적으로 안 함 — 문서 출력 시 호출자가 None 체크하도록.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.company.models import CompanyProfile
from app.modules.company.schemas import CompanyProfileIn, CompanyProfileOut
from app.modules.tenants.router import get_current_tenant_id

router = APIRouter(
    prefix="/api/company-profile",
    tags=["company"],
    dependencies=[Depends(get_current_internal_user)],
)


def get_company_profile(
    db: Session, tenant_id: int | None
) -> CompanyProfile | None:
    """Resolve the active company profile.

    Lookup order:
      1. exact tenant_id match (if header X-Tenant-ID is set)
      2. global row (tenant_id IS NULL) — fallback for single-tenant installs
    """
    if tenant_id is not None:
        row = (
            db.query(CompanyProfile)
            .filter(CompanyProfile.tenant_id == tenant_id)
            .first()
        )
        if row:
            return row
    return db.query(CompanyProfile).filter(CompanyProfile.tenant_id.is_(None)).first()


@router.get("", response_model=CompanyProfileOut)
def read_profile(
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    row = get_company_profile(db, tenant_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="회사정보가 설정되어 있지 않습니다. PUT /api/company-profile 로 등록하세요.",
        )
    return row


@router.put(
    "",
    response_model=CompanyProfileOut,
    dependencies=[Depends(require_role("admin"))],
)
def upsert_profile(
    payload: CompanyProfileIn,
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    row = get_company_profile(db, tenant_id)
    if row is None:
        row = CompanyProfile(tenant_id=tenant_id, **payload.model_dump())
        db.add(row)
    else:
        for k, v in payload.model_dump().items():
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row
