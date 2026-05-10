"""BOM + Work Order endpoints.

Releasing a WorkOrder consumes BOM components from stock (outbound movement)
and on completion produces the finished good (inbound movement).
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    require_module_role,
    require_role,
)
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.inventory.models import Item, MovementType
from app.modules.inventory.schemas import StockMovementCreate
from app.modules.inventory.service import create_movement
from app.modules.manufacturing.models import (
    BillOfMaterials,
    BomComponent,
    WorkOrder,
    WorkOrderStatus,
)

router = APIRouter(
    prefix="/api/manufacturing",
    tags=["manufacturing"],
    dependencies=[Depends(get_current_internal_user)],
)


# Schemas


class BomComponentIn(BaseModel):
    component_item_id: int
    quantity_per: Decimal
    notes: str | None = None


class BomComponentOut(BomComponentIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BomIn(BaseModel):
    finished_item_id: int
    version: str = "v1"
    output_quantity: Decimal = Decimal("1")
    notes: str | None = None
    components: list[BomComponentIn] = Field(min_length=1)


class BomOut(BaseModel):
    id: int
    finished_item_id: int
    version: str
    output_quantity: Decimal
    notes: str | None
    is_active: bool
    components: list[BomComponentOut]
    model_config = ConfigDict(from_attributes=True)


class WorkOrderIn(BaseModel):
    wo_no: str
    bom_id: int
    quantity: Decimal
    notes: str | None = None


class WorkOrderOut(BaseModel):
    id: int
    wo_no: str
    bom_id: int
    quantity: Decimal
    status: WorkOrderStatus
    started_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    model_config = ConfigDict(from_attributes=True)


# BOM endpoints


@router.get("/boms", response_model=Page[BomOut])
def list_boms(params: PageParams = Depends(), db: Session = Depends(get_db)):
    q = (
        db.query(BillOfMaterials)
        .options(selectinload(BillOfMaterials.components))
        .order_by(BillOfMaterials.finished_item_id, BillOfMaterials.version)
    )
    return paginate(q, params)


@router.post(
    "/boms",
    response_model=BomOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_bom(payload: BomIn, db: Session = Depends(get_db)):
    if not db.query(Item).filter(Item.id == payload.finished_item_id).first():
        raise HTTPException(status_code=404, detail="Finished item not found")
    bom = BillOfMaterials(
        finished_item_id=payload.finished_item_id,
        version=payload.version,
        output_quantity=payload.output_quantity,
        notes=payload.notes,
    )
    for c in payload.components:
        bom.components.append(BomComponent(**c.model_dump()))
    db.add(bom)
    db.commit()
    db.refresh(bom)
    return bom


# Work order endpoints


@router.get("/work-orders", response_model=Page[WorkOrderOut])
def list_work_orders(params: PageParams = Depends(), db: Session = Depends(get_db)):
    return paginate(
        db.query(WorkOrder).order_by(WorkOrder.created_at.desc()), params
    )


@router.post(
    "/work-orders",
    response_model=WorkOrderOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def create_work_order(payload: WorkOrderIn, db: Session = Depends(get_db)):
    if not db.query(BillOfMaterials).filter(BillOfMaterials.id == payload.bom_id).first():
        raise HTTPException(status_code=404, detail="BOM not found")
    if db.query(WorkOrder).filter(WorkOrder.wo_no == payload.wo_no).first():
        raise HTTPException(status_code=400, detail="WO no already exists")
    wo = WorkOrder(
        wo_no=payload.wo_no,
        bom_id=payload.bom_id,
        quantity=payload.quantity,
        notes=payload.notes,
    )
    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


@router.post(
    "/work-orders/{wo_id}/release",
    response_model=WorkOrderOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def release_work_order(wo_id: int, db: Session = Depends(get_db)):
    """Consume BOM components from stock (outbound movements).

    Pre-flight: lock the WO, BOM, and every component item, and verify each
    has sufficient stock before issuing any movement. This prevents the
    create_movement() loop from partially consuming inventory if a later
    component is short.
    """
    wo = db.query(WorkOrder).filter(WorkOrder.id == wo_id).with_for_update().first()
    if not wo:
        raise HTTPException(status_code=404, detail="WO not found")
    if wo.status != WorkOrderStatus.draft:
        raise HTTPException(status_code=400, detail=f"Cannot release {wo.status.value}")
    bom = (
        db.query(BillOfMaterials)
        .options(selectinload(BillOfMaterials.components))
        .filter(BillOfMaterials.id == wo.bom_id)
        .with_for_update()
        .first()
    )
    units = (Decimal(wo.quantity) / Decimal(bom.output_quantity)).quantize(
        Decimal("0.0001")
    )

    # Pre-flight: lock & verify each component's stock
    from app.modules.inventory.models import Item

    needs: list[tuple[int, Decimal]] = [
        (c.component_item_id, Decimal(c.quantity_per) * units) for c in bom.components
    ]
    for item_id, qty in needs:
        item = (
            db.query(Item).filter(Item.id == item_id).with_for_update().first()
        )
        if not item:
            raise HTTPException(status_code=404, detail=f"Component item {item_id} not found")
        if Decimal(item.stock_qty) < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for item {item_id}: {item.stock_qty} < {qty}",
            )

    # All checks passed; now consume.
    for item_id, qty in needs:
        try:
            create_movement(
                db,
                StockMovementCreate(
                    item_id=item_id,
                    type=MovementType.outbound,
                    quantity=qty,
                    note=f"WO {wo.wo_no} consume",
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    wo.status = WorkOrderStatus.in_progress
    wo.started_at = datetime.utcnow()
    db.commit()
    db.refresh(wo)
    return wo


@router.post(
    "/work-orders/{wo_id}/complete",
    response_model=WorkOrderOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def complete_work_order(wo_id: int, db: Session = Depends(get_db)):
    """Produce the finished good (inbound movement)."""
    wo = db.query(WorkOrder).filter(WorkOrder.id == wo_id).with_for_update().first()
    if not wo:
        raise HTTPException(status_code=404, detail="WO not found")
    if wo.status != WorkOrderStatus.in_progress:
        raise HTTPException(status_code=400, detail=f"Cannot complete {wo.status.value}")
    bom = (
        db.query(BillOfMaterials)
        .filter(BillOfMaterials.id == wo.bom_id)
        .with_for_update()
        .first()
    )
    try:
        create_movement(
            db,
            StockMovementCreate(
                item_id=bom.finished_item_id,
                type=MovementType.inbound,
                quantity=wo.quantity,
                note=f"WO {wo.wo_no} produce",
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    wo.status = WorkOrderStatus.completed
    wo.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(wo)
    return wo
