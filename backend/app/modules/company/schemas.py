from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class CompanyProfileOut(CompanyProfileIn):
    id: int
    tenant_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
