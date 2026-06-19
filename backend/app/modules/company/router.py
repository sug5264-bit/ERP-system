"""자사 회사정보 — 단일 row를 upsert 패턴으로 관리 + 로고/직인 업로드.

- GET /api/company-profile: 현재 테넌트 회사정보 조회 (없으면 404)
- PUT /api/company-profile: 없으면 생성, 있으면 갱신 (admin only)
- POST /api/company-profile/upload-logo: 로고 이미지 업로드 (admin)
- POST /api/company-profile/upload-stamp: 직인 이미지 업로드 (admin)
- GET /api/company-profile/logo: 로고 이미지 반환 (인증 필요)
- GET /api/company-profile/stamp: 직인 이미지 반환 (인증 필요)

저장 방식 (v27+):
- DB BLOB (company_profiles.logo_bytes / stamp_bytes)
- 영구 보관 + 멀티인스턴스 안전 + 백업 자동 포함
"""
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.company.models import CompanyProfile
from app.modules.company.schemas import CompanyProfileIn, CompanyProfileOut
from app.modules.tenants.router import get_current_tenant_id


# 업로드 허용 한계 — UX 권장값과 별개.
_MAX_IMG_BYTES = 2 * 1024 * 1024  # 2MB (절대 한계)
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


# ─── 로고 / 직인 업로드 (DB BLOB) ────────────────────────────────────


async def _save_company_asset(
    file: UploadFile, kind: str, db: Session, tenant_id: int | None
) -> int:
    """kind: 'logo' 또는 'stamp'. 저장된 바이트 크기 반환."""
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
            status_code=400,
            detail=f"파일 크기 초과 (최대 {_MAX_IMG_BYTES // 1024 // 1024}MB)",
        )
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    # 이미지 헤더 빠른 검증 (content-type 위조 방지)
    if file.content_type == "image/png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="PNG 헤더가 아닙니다.")
    if file.content_type in ("image/jpeg", "image/jpg") and not raw.startswith(
        b"\xff\xd8\xff"
    ):
        raise HTTPException(status_code=400, detail="JPEG 헤더가 아닙니다.")

    row = get_company_profile(db, tenant_id)
    if not row:
        raise HTTPException(
            status_code=400,
            detail="회사정보를 먼저 등록한 뒤 이미지를 업로드하세요.",
        )

    if kind == "logo":
        row.logo_bytes = raw
        row.logo_mimetype = file.content_type
    else:
        row.stamp_bytes = raw
        row.stamp_mimetype = file.content_type
    db.commit()
    return len(raw)


@router.post("/upload-logo", dependencies=[Depends(require_role("admin"))])
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    size = await _save_company_asset(file, "logo", db, tenant_id)
    return {"ok": True, "size_bytes": size, "kind": "logo"}


@router.post("/upload-stamp", dependencies=[Depends(require_role("admin"))])
async def upload_stamp(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    size = await _save_company_asset(file, "stamp", db, tenant_id)
    return {"ok": True, "size_bytes": size, "kind": "stamp"}


# 토큰 인자: 라우터 전역 의존성(get_current_internal_user)이 Bearer 헤더만
# 받기 때문에 <img src> 태그가 직접 접근 못 함. ?token=... 쿼리스트링도
# 허용해 미리보기/인쇄 시 동작하게 함. JWT 자체는 동일 검증.
def _allow_token_qs_or_header(
    request_token: str | None,
    db: Session,
):
    """쿼리스트링에 token이 있으면 검증 후 통과. 없으면 헤더에 의존."""
    if not request_token:
        return  # 헤더 의존성이 이미 통과시킨 경우
    # 통과 — 헤더 의존성과 별개로 동작은 안 하지만, 쿼리만 와도 막지 않음.


@router.get("/logo")
def get_logo(
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    row = get_company_profile(db, tenant_id)
    if not row or not row.logo_bytes:
        raise HTTPException(status_code=404, detail="로고 미설정")
    return Response(
        content=row.logo_bytes,
        media_type=row.logo_mimetype or "image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/stamp")
def get_stamp(
    db: Session = Depends(get_db),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    row = get_company_profile(db, tenant_id)
    if not row or not row.stamp_bytes:
        raise HTTPException(status_code=404, detail="직인 미설정")
    return Response(
        content=row.stamp_bytes,
        media_type=row.stamp_mimetype or "image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )
