from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class ContractType(str, PyEnum):
    customer = "customer"      # 매출 계약
    supplier = "supplier"      # 매입 계약
    employment = "employment"  # 고용 계약
    lease = "lease"            # 임대차 계약
    other = "other"


class ContractStatus(str, PyEnum):
    draft = "draft"
    active = "active"
    expired = "expired"
    terminated = "terminated"


class RenewalType(str, PyEnum):
    none = "none"
    manual = "manual"     # 협의 후 갱신
    auto = "auto"         # 자동 갱신


class Contract(BaseEntity):
    __tablename__ = "contracts"

    contract_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[ContractType] = mapped_column(
        Enum(ContractType), default=ContractType.other, nullable=False, index=True
    )
    counterparty: Mapped[str] = mapped_column(String(200), nullable=False)
    # Either customer/supplier/employee linkage (one of)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales_customers.id"), index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("hr_employees.id"))

    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="KRW")
    payment_terms: Mapped[str | None] = mapped_column(String(500))

    renewal: Mapped[RenewalType] = mapped_column(
        Enum(RenewalType), default=RenewalType.manual, nullable=False
    )
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus), default=ContractStatus.draft, nullable=False, index=True
    )
    sla_response_hours: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(2000))
    document_url: Mapped[str | None] = mapped_column(String(500))
