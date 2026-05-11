from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class EliminationType(str, PyEnum):
    intercompany_sales = "intercompany_sales"  # 내부거래 매출/매입 상계
    intercompany_ar_ap = "intercompany_ar_ap"  # 내부 채권/채무 상계
    investment = "investment"                    # 모회사 투자 vs 자회사 자본
    other = "other"


class EliminationEntry(BaseEntity):
    """Consolidation elimination — removes intercompany duplication."""

    __tablename__ = "cons_elimination_entries"

    period_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    type: Mapped[EliminationType] = mapped_column(
        Enum(EliminationType), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    debit_account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    credit_account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    entity_a_tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"))
    entity_b_tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"))


class TaxAdjustment(BaseEntity):
    """세무조정: 회계이익 → 과세표준 (가산조정 / 차감조정)."""

    __tablename__ = "cons_tax_adjustments"

    period_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    # 가산조정 = +, 차감조정 = -
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="permanent")  # permanent | temporary
    notes: Mapped[str | None] = mapped_column(String(1000))
