"""자사 회사정보 — 단일 row를 upsert 패턴으로 관리 + 로고/직인 업로드.

- GET /api/company-profile: 현재 테넌트 회사정보 조회 (없으면 404)
- PUT /api/company-profile: 없으면 생성, 있으면 갱신 (admin only)
- POST /api/company-profile/upload-logo: 로고 이미지 업로드 (admin)
- POST /api/company-profile/upload-stamp: 직인 이미지 업로드 (admin)
- GET /api/company-profile/logo: 로고 이미지 반환 (인증 필요)
- GET /api/company-profile/stamp: 직인 이미지 반환 (인증 필요)
"""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.company.models import CompanyProfile
from app.modules.company.schemas import CompanyProfileIn, CompanyProfileOut
from app.modules.tenants.router import get_current_tenant_id


_COMPANY_ASSETS_DIR = Path(
    os.environ.get("COMPANY_ASSETS_DIR", "/tmp/erp_company_assets")
)
_COMPANY_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
_MAX_IMG_BYTES = 2 * 1024 * 1024  # 2MB
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}

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
            # 로고/직인 경로는 PUT으로 덮어쓰지 않음 (별도 업로드 엔드포인트)
            if k in ("logo_path", "stamp_path") and v is None:
                continue
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── 로고 / 직인 업로드 ─────────────────────────────────────────────


async def _save_company_asset(
    file: UploadFile, kind: str, db: Session, tenant_id: int | None
) -> str:
    """kind: 'logo' 또는 'stamp'. 저장 후 절대경로 반환."""
    if kind not in ("logo", "stamp"):
        raise HTTPException(status_code=400, detail="kind must be logo or stamp")
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"PNG 또는 JPG만 허용 (수신: {file.content_type})",
        )
    raw = await file.read()
    if len(raw) > _MAX_IMG_BYTES:
        raise HTTPException(
            status_code=400, detail=f"파일 크기 초과 (최대 {_MAX_IMG_BYTES // 1024}KB)"
        )

    row = get_company_profile(db, tenant_id)
    if not row:
        raise HTTPException(
            status_code=400,
            detail="회사정보를 먼저 등록한 뒤 이미지를 업로드하세요.",
        )

    ext = "png" if file.content_type == "image/png" else "jpg"
    suffix = f"_t{tenant_id}" if tenant_id else ""
    target = _COMPANY_ASSETS_DIR / f"{kind}{suffix}.{ext}"
    # 기존 다른 확장자 파일 정리 (덮어쓰기)
    for old in _COMPANY_ASSETS_DIR.glob(f"{kind}{suffix}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    target.write_bytes(raw)

    if kind == "logo":
        row.logo_path = str(target)
    else:
        row.stamp_path = str(target)
    db.commit()
    return str(target)


@router.post("/upload-logo", dependencies=[Depends(require_role("admin"))])
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    path = await _save_company_asset(file, "logo", db, tenant_id)
    return {"ok": True, "path": path}


@router.post("/upload-stamp", dependencies=[Depends(require_role("admin"))])
async def upload_stamp(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    path = await _save_company_asset(file, "stamp", db, tenant_id)
    return {"ok": True, "path": path}


@router.get("/logo")
def get_logo(
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    row = get_company_profile(db, tenant_id)
    if not row or not row.logo_path or not Path(row.logo_path).exists():
        raise HTTPException(status_code=404, detail="로고 미설정")
    return FileResponse(row.logo_path)


@router.get("/stamp")
def get_stamp(
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    row = get_company_profile(db, tenant_id)
    if not row or not row.stamp_path or not Path(row.stamp_path).exists():
        raise HTTPException(status_code=404, detail="직인 미설정")
    return FileResponse(row.stamp_path)
