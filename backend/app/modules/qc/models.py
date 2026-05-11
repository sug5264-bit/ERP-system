from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class InspectionStage(str, PyEnum):
    incoming = "incoming"        # 수입검사 (입고 시)
    in_process = "in_process"    # 공정검사 (제조 중)
    final = "final"              # 출하검사 (출고 전)


class InspectionResult(str, PyEnum):
    pending = "pending"
    pass_ = "pass"
    fail = "fail"
    rework = "rework"


class InspectionPlan(BaseEntity):
    """A reusable checklist for inspecting a given item at a given stage.

    Each plan owns a list of `InspectionCriterion` rows defining what to
    measure (e.g., 길이 ≥ 10mm, 무게 ±0.1g).
    """

    __tablename__ = "qc_inspection_plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("inv_items.id"))
    stage: Mapped[InspectionStage] = mapped_column(
        Enum(InspectionStage), default=InspectionStage.incoming, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(String(1000))

    criteria: Mapped[list["InspectionCriterion"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class InspectionCriterion(BaseEntity):
    """A single measurable item on an InspectionPlan."""

    __tablename__ = "qc_inspection_criteria"

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("qc_inspection_plans.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    measurement_type: Mapped[str] = mapped_column(String(20), default="numeric")
    # numeric | boolean | text
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    expected_text: Mapped[str | None] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[InspectionPlan] = relationship(back_populates="criteria")


class Inspection(BaseEntity):
    """An execution of an InspectionPlan against a specific lot / work-order /
    GR. Result is computed from per-criterion measurements."""

    __tablename__ = "qc_inspections"

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("qc_inspection_plans.id"), nullable=False, index=True
    )
    stage: Mapped[InspectionStage] = mapped_column(
        Enum(InspectionStage), nullable=False, index=True
    )
    item_id: Mapped[int | None] = mapped_column(ForeignKey("inv_items.id"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inv_lots.id"))
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("mfg_work_orders.id"))
    gr_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_goods_receipts.id"))
    quantity_inspected: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    quantity_passed: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    quantity_failed: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime)
    result: Mapped[InspectionResult] = mapped_column(
        Enum(InspectionResult), default=InspectionResult.pending,
        nullable=False, index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(2000))

    measurements: Mapped[list["InspectionMeasurement"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class InspectionMeasurement(BaseEntity):
    """A single criterion result on a specific Inspection."""

    __tablename__ = "qc_inspection_measurements"

    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("qc_inspections.id"), nullable=False, index=True
    )
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("qc_inspection_criteria.id"), nullable=False
    )
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    boolean_value: Mapped[bool | None] = mapped_column()
    text_value: Mapped[str | None] = mapped_column(String(500))
    passed: Mapped[bool] = mapped_column(default=False)

    inspection: Mapped[Inspection] = relationship(back_populates="measurements")


class DefectLog(BaseEntity):
    """Tracks defects found during inspection — feeds vendor scorecards
    and Pareto analysis."""

    __tablename__ = "qc_defect_logs"

    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("qc_inspections.id"), nullable=False, index=True
    )
    defect_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    description: Mapped[str | None] = mapped_column(String(2000))
    action: Mapped[str | None] = mapped_column(String(50))  # rework | scrap | return
    reported_at: Mapped[date] = mapped_column(Date, default=date.today)
