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


# ---- MRP: forecast → MPS → material requirements --------------------------


from app.modules.manufacturing.models import (  # noqa: E402
    DemandForecast,
    MasterProductionSchedule,
    MaterialRequirement,
)


class ForecastIn(BaseModel):
    item_id: int
    period_code: str
    forecast_qty: Decimal
    notes: str | None = None


class ForecastOut(ForecastIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


@router.get("/forecasts", response_model=list[ForecastOut])
def list_forecasts(
    period_code: str | None = None,
    item_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(DemandForecast).order_by(
        DemandForecast.period_code, DemandForecast.item_id
    )
    if period_code:
        q = q.filter(DemandForecast.period_code == period_code)
    if item_id is not None:
        q = q.filter(DemandForecast.item_id == item_id)
    return q.all()


@router.post(
    "/forecasts",
    response_model=ForecastOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def upsert_forecast(payload: ForecastIn, db: Session = Depends(get_db)):
    if payload.forecast_qty < 0:
        raise HTTPException(status_code=400, detail="forecast_qty must be >= 0")
    f = (
        db.query(DemandForecast)
        .filter(
            DemandForecast.item_id == payload.item_id,
            DemandForecast.period_code == payload.period_code,
        )
        .with_for_update()
        .first()
    )
    if f:
        f.forecast_qty = payload.forecast_qty
        f.notes = payload.notes
    else:
        f = DemandForecast(**payload.model_dump())
        db.add(f)
    db.commit()
    db.refresh(f)
    return f


@router.post(
    "/mrp-run",
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def mrp_run(period_code: str, db: Session = Depends(get_db)):
    """Run MRP for `period_code`:
      1. For each forecast in this period, compute MPS = max(0, forecast - on_hand + safety_stock).
      2. Explode MPS through active BOM to get gross component requirements.
      3. Net out current inventory of each component.
      4. Persist MasterProductionSchedule + MaterialRequirement rows (idempotent).

    Returns a summary; previous MPS/MR rows for this period are replaced.
    """
    from app.modules.inventory.models import Item, ItemPolicy

    # Wipe previous run for this period (idempotent)
    db.query(MasterProductionSchedule).filter(
        MasterProductionSchedule.period_code == period_code
    ).delete()
    db.query(MaterialRequirement).filter(
        MaterialRequirement.period_code == period_code
    ).delete()
    db.flush()

    forecasts = (
        db.query(DemandForecast)
        .filter(DemandForecast.period_code == period_code)
        .all()
    )
    if not forecasts:
        return {"period_code": period_code, "mps_count": 0, "mr_count": 0,
                "note": "no forecasts for this period"}

    mps_rows: list[MasterProductionSchedule] = []
    component_demand: dict[int, Decimal] = {}

    for f in forecasts:
        item = db.query(Item).filter(Item.id == f.item_id).first()
        if not item:
            continue
        on_hand = Decimal(item.stock_qty)
        pol = (
            db.query(ItemPolicy)
            .filter(ItemPolicy.item_id == f.item_id)
            .first()
        )
        safety = Decimal(pol.safety_stock) if pol else Decimal("0")
        net = max(Decimal("0"), Decimal(f.forecast_qty) + safety - on_hand)
        if net <= 0:
            continue
        mps = MasterProductionSchedule(
            item_id=f.item_id, period_code=period_code, planned_qty=net,
            notes=f"forecast={f.forecast_qty} on_hand={on_hand} safety={safety}",
        )
        db.add(mps)
        mps_rows.append(mps)

        # Explode active BOM
        bom = (
            db.query(BillOfMaterials)
            .options(selectinload(BillOfMaterials.components))
            .filter(
                BillOfMaterials.finished_item_id == f.item_id,
                BillOfMaterials.is_active.is_(True),
            )
            .order_by(BillOfMaterials.id.desc())
            .first()
        )
        if not bom:
            continue
        units = (net / Decimal(bom.output_quantity)).quantize(Decimal("0.0001"))
        for comp in bom.components:
            need = Decimal(comp.quantity_per) * units
            component_demand[comp.component_item_id] = (
                component_demand.get(comp.component_item_id, Decimal("0")) + need
            )

    # Net components against on-hand
    mr_count = 0
    for comp_id, gross in component_demand.items():
        comp_item = db.query(Item).filter(Item.id == comp_id).first()
        on_hand = Decimal(comp_item.stock_qty) if comp_item else Decimal("0")
        net = max(Decimal("0"), gross - on_hand)
        db.add(MaterialRequirement(
            period_code=period_code, item_id=comp_id,
            gross_required=gross, on_hand=on_hand, net_required=net,
        ))
        mr_count += 1

    db.commit()
    return {
        "period_code": period_code,
        "mps_count": len(mps_rows),
        "mr_count": mr_count,
    }


@router.get("/mps")
def list_mps(period_code: str, db: Session = Depends(get_db)):
    rows = (
        db.query(MasterProductionSchedule)
        .filter(MasterProductionSchedule.period_code == period_code)
        .order_by(MasterProductionSchedule.item_id)
        .all()
    )
    return [
        {
            "id": r.id, "item_id": r.item_id, "period_code": r.period_code,
            "planned_qty": float(r.planned_qty), "notes": r.notes,
        }
        for r in rows
    ]


@router.get("/material-requirements")
def list_material_requirements(period_code: str, db: Session = Depends(get_db)):
    rows = (
        db.query(MaterialRequirement)
        .filter(MaterialRequirement.period_code == period_code)
        .order_by(MaterialRequirement.item_id)
        .all()
    )
    return [
        {
            "id": r.id, "item_id": r.item_id, "period_code": r.period_code,
            "gross_required": float(r.gross_required),
            "on_hand": float(r.on_hand),
            "net_required": float(r.net_required),
        }
        for r in rows
    ]
