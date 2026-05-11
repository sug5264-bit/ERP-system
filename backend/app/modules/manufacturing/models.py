"""Bill of Materials (BOM) + Work Order skeleton.

A BOM ties a finished good (item) to its component items + quantities.
A WorkOrder consumes those components from inventory and produces the finished good.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.base_model import BaseEntity


class WorkOrderStatus(str, PyEnum):
    draft = "draft"
    released = "released"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class BillOfMaterials(BaseEntity):
    __tablename__ = "mfg_boms"

    finished_item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(20), default="v1")
    output_quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=1)
    notes: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True)

    components: Mapped[list["BomComponent"]] = relationship(
        back_populates="bom", cascade="all, delete-orphan"
    )


class BomComponent(BaseEntity):
    __tablename__ = "mfg_bom_components"

    bom_id: Mapped[int] = mapped_column(
        ForeignKey("mfg_boms.id"), nullable=False, index=True
    )
    component_item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False
    )
    quantity_per: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255))

    bom: Mapped[BillOfMaterials] = relationship(back_populates="components")


class WorkOrder(BaseEntity):
    __tablename__ = "mfg_work_orders"

    wo_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    bom_id: Mapped[int] = mapped_column(ForeignKey("mfg_boms.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus), default=WorkOrderStatus.draft, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(String(1000))


class DemandForecast(BaseEntity):
    """Forecasted demand for a finished item over a future period (week or month)."""

    __tablename__ = "mfg_demand_forecasts"
    __table_args__ = (
        UniqueConstraint("item_id", "period_code", name="uq_demand_item_period"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False, index=True
    )
    period_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # "2026-W20" or "2026-05"
    forecast_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))


class MasterProductionSchedule(BaseEntity):
    """MPS: planned production qty per finished item per period.

    Created by an MRP run from forecasts net of on-hand stock + safety stock.
    """

    __tablename__ = "mfg_mps"
    __table_args__ = (
        UniqueConstraint("item_id", "period_code", name="uq_mps_item_period"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False, index=True
    )
    period_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))


class MaterialRequirement(BaseEntity):
    """Net component requirement after MRP explosion of MPS through BOM."""

    __tablename__ = "mfg_mrp_requirements"

    period_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False, index=True
    )
    gross_required: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    net_required: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)


class WorkCenter(BaseEntity):
    """A physical work-center: a machine, line, or station with finite capacity.

    `capacity_per_day` is in minutes — e.g., 480 min = 8h shift x 1 machine.
    """

    __tablename__ = "mfg_work_centers"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    capacity_per_day: Mapped[int] = mapped_column(Integer, default=480)
    is_active: Mapped[bool] = mapped_column(default=True)


class RoutingStep(BaseEntity):
    """An ordered step required to produce a BOM finished item. Defines which
    work-center, how long (setup + run per unit), and the sequence.
    """

    __tablename__ = "mfg_routing_steps"
    __table_args__ = (
        UniqueConstraint("bom_id", "sequence", name="uq_routing_bom_seq"),
    )

    bom_id: Mapped[int] = mapped_column(
        ForeignKey("mfg_boms.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    work_center_id: Mapped[int] = mapped_column(
        ForeignKey("mfg_work_centers.id"), nullable=False
    )
    setup_minutes: Mapped[int] = mapped_column(Integer, default=0)
    run_minutes_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), default=Decimal("1")
    )


class ShopFloorOpStatus(str, PyEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    paused = "paused"


class ShopFloorOp(BaseEntity):
    """One operation against a specific WorkOrder. Created automatically when
    a WO is released — one per RoutingStep. Operators clock in/out to track
    actual minutes vs planned."""

    __tablename__ = "mfg_shop_floor_ops"

    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("mfg_work_orders.id"), nullable=False, index=True
    )
    routing_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("mfg_routing_steps.id")
    )
    work_center_id: Mapped[int] = mapped_column(
        ForeignKey("mfg_work_centers.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[ShopFloorOpStatus] = mapped_column(
        Enum(ShopFloorOpStatus), default=ShopFloorOpStatus.pending,
        nullable=False, index=True,
    )
