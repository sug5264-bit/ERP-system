from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class DepreciationMethod(str, PyEnum):
    straight_line = "straight_line"
    declining_balance = "declining_balance"


class AssetStatus(str, PyEnum):
    active = "active"
    disposed = "disposed"


class AssetCategory(BaseEntity):
    __tablename__ = "fa_categories"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_useful_life_months: Mapped[int] = mapped_column(Integer, default=60)
    default_method: Mapped[DepreciationMethod] = mapped_column(
        Enum(DepreciationMethod), default=DepreciationMethod.straight_line
    )


class Asset(BaseEntity):
    """A physical/fixed asset that depreciates over its useful life.

    Book value = acquired_cost - accumulated_depreciation. Once it reaches
    salvage_value, depreciation stops.
    """

    __tablename__ = "fa_assets"

    asset_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("fa_categories.id"))
    acquired_date: Mapped[date] = mapped_column(Date, nullable=False)
    acquired_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[DepreciationMethod] = mapped_column(
        Enum(DepreciationMethod), default=DepreciationMethod.straight_line
    )
    accumulated_depreciation: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0")
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus), default=AssetStatus.active, nullable=False
    )
    disposed_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(1000))

    category: Mapped["AssetCategory | None"] = relationship()


class DepreciationEntry(BaseEntity):
    """One row per (asset, period) — idempotent monthly run."""

    __tablename__ = "fa_depreciation_entries"
    __table_args__ = (
        UniqueConstraint("asset_id", "period_code", name="uq_dep_asset_period"),
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("fa_assets.id"), nullable=False, index=True
    )
    period_code: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("fin_journal_entries.id")
    )
