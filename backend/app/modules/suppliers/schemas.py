from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.business_no import format_business_no, is_valid_business_no
from app.modules.suppliers.models import POStatus


def _check_biz_no(v: str | None) -> str | None:
    if v is None or v.strip() == "":
        return None
    if not is_valid_business_no(v):
        raise ValueError("유효한 사업자등록번호가 아닙니다 (체크섬 불일치)")
    return format_business_no(v)


class SupplierIn(BaseModel):
    code: str
    name: str
    contact_email: EmailStr | None = None
    phone: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    portal_user_id: int | None = None

    @field_validator("business_no")
    @classmethod
    def _validate_business_no(cls, v: str | None) -> str | None:
        return _check_biz_no(v)


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_email: EmailStr | None = None
    phone: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    is_active: bool | None = None

    @field_validator("business_no")
    @classmethod
    def _validate_business_no(cls, v: str | None) -> str | None:
        return _check_biz_no(v)


class CreateSupplierWithPortalUser(BaseModel):
    """Create a Supplier together with a fresh portal-user account."""
    code: str
    name: str
    contact_email: EmailStr
    phone: str | None = None
    business_no: str | None = None
    portal_full_name: str
    portal_password: str = Field(min_length=8)


class SupplierOut(SupplierIn):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class POItemIn(BaseModel):
    item_id: int
    quantity: Decimal
    unit_price: Decimal


class POItemOut(POItemIn):
    id: int
    received_qty: Decimal

    model_config = ConfigDict(from_attributes=True)


class POCreate(BaseModel):
    po_no: str
    supplier_id: int
    expected_date: date | None = None
    notes: str | None = None
    items: list[POItemIn] = Field(min_length=1)


class POOut(BaseModel):
    id: int
    po_no: str
    supplier_id: int
    order_date: date
    expected_date: date | None
    status: POStatus
    total: Decimal
    notes: str | None
    items: list[POItemOut]
    supplier: SupplierOut | None = None

    model_config = ConfigDict(from_attributes=True)


class POReceiveLine(BaseModel):
    item_id: int
    quantity: Decimal


class POReceive(BaseModel):
    lines: list[POReceiveLine] = Field(min_length=1)
