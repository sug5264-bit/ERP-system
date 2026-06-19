"""자사 회사 정보 — 거래명세표/세금계산서 등 문서 출력에 사용.

전사 단위 1행이 기본 (id=1). 멀티테넌트 환경에서는 tenant_id별 1행.
"""
from sqlalchemy import ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class CompanyProfile(BaseEntity):
    """국세청 세금계산서 표준에 맞춘 회사 기본정보.

    필드는 한국 사업자등록증 + 세금계산서 양식 기준.
    """

    __tablename__ = "company_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_company_profile_tenant"),
    )

    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id"), index=True
    )

    # 사업자등록증 항목
    business_no: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 사업자등록번호 (10자리, 'XXX-XX-XXXXX')
    corporate_no: Mapped[str | None] = mapped_column(String(20))  # 법인등록번호
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)  # 상호
    representative: Mapped[str] = mapped_column(String(100), nullable=False)  # 대표자
    address: Mapped[str] = mapped_column(String(500), nullable=False)  # 사업장 주소
    business_type: Mapped[str | None] = mapped_column(String(100))  # 업태
    business_item: Mapped[str | None] = mapped_column(String(200))  # 종목

    # 연락처
    phone: Mapped[str | None] = mapped_column(String(50))
    fax: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))

    # 금융 정보 (세금계산서/거래명세표 입금계좌)
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_account: Mapped[str | None] = mapped_column(String(100))
    bank_holder: Mapped[str | None] = mapped_column(String(100))

    # 시각 자산 — DB BLOB 저장 (영구 보관, 멀티인스턴스 안전, 백업에 포함)
    logo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    logo_mimetype: Mapped[str | None] = mapped_column(String(50))
    stamp_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    stamp_mimetype: Mapped[str | None] = mapped_column(String(50))

    # Deprecated — 이전 경로기반 저장 (v23~v26 호환). v27부터 사용 안 함.
    logo_path: Mapped[str | None] = mapped_column(String(500))
    stamp_path: Mapped[str | None] = mapped_column(String(500))
