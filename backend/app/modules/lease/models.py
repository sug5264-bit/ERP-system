from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class LeaseStatus(str, PyEnum):
    draft = "draft"
    active = "active"
    terminated = "terminated"


class Lease(BaseEntity):
    """A leased asset under IFRS 16. Lessee records both ROU asset and a
    lease liability discounted at incremental borrowing rate (IBR)."""

    __tablename__ = "lease_contracts"

    lease_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    annual_discount_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.05"))
    initial_direct_costs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    rou_asset: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    lease_liability: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    accumulated_depreciation: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    status: Mapped[LeaseStatus] = mapped_column(
        Enum(LeaseStatus), default=LeaseStatus.draft, nullable=False, index=True
    )
    counterparty: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(1000))

    schedule: Mapped[list["LeaseScheduleEntry"]] = relationship(
        back_populates="lease", cascade="all, delete-orphan",
        order_by="LeaseScheduleEntry.period_code",
    )


class LeaseScheduleEntry(BaseEntity):
    """Per-month amortization row generated when the lease is activated."""

    __tablename__ = "lease_schedule_entries"
    __table_args__ = (
        UniqueConstraint("lease_id", "period_code", name="uq_lease_period"),
    )

    lease_id: Mapped[int] = mapped_column(
        ForeignKey("lease_contracts.id"), nullable=False, index=True
    )
    period_code: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_liability: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interest_expense: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    principal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    closing_liability: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    depreciation: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    posted: Mapped[bool] = mapped_column(default=False)
    journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("fin_journal_entries.id")
    )

    lease: Mapped[Lease] = relationship(back_populates="schedule")
