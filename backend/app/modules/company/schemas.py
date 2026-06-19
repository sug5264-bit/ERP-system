from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.business_no import format_business_no, is_valid_business_no


class CompanyProfileIn(BaseModel):
    business_no: str = Field(min_length=10, max_length=20)
    corporate_no: str | None = None
    company_name: str
    representative: str
    address: str
    business_type: str | None = None
    business_item: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    bank_holder: str | None = None
    logo_path: str | None = None
    stamp_path: str | None = None

    @field_validator("business_no")
    @classmethod
    def _validate_biz_no(cls, v: str) -> str:
        if not is_valid_business_no(v):
            raise ValueError(
                "유효한 사업자등록번호가 아닙니다 (체크섬 불일치 또는 형식 오류)"
            )
        return format_business_no(v)


class CompanyProfileOut(CompanyProfileIn):
    id: int
    tenant_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
