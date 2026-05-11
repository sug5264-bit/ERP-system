"""QC endpoints: plans, inspections, defects, pass-rate analytics."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    get_current_user,
    require_module_role,
    require_role,
)
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.auth.models import User
from app.modules.qc.models import (
    DefectLog,
    Inspection,
    InspectionCriterion,
    InspectionMeasurement,
    InspectionPlan,
    InspectionResult,
    InspectionStage,
)

router = APIRouter(
    prefix="/api/qc",
    tags=["qc"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class CriterionIn(BaseModel):
    name: str
    measurement_type: str = "numeric"
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    expected_text: str | None = None
    sequence: int = 0


class CriterionOut(CriterionIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class PlanIn(BaseModel):
    code: str
    name: str
    item_id: int | None = None
    stage: InspectionStage = InspectionStage.incoming
    notes: str | None = None
    criteria: list[CriterionIn] = Field(min_length=1)


class PlanOut(BaseModel):
    id: int
    code: str
    name: str
    item_id: int | None
    stage: InspectionStage
    is_active: bool
    notes: str | None
    criteria: list[CriterionOut]
    model_config = ConfigDict(from_attributes=True)


class MeasurementIn(BaseModel):
    criterion_id: int
    numeric_value: Decimal | None = None
    boolean_value: bool | None = None
    text_value: str | None = None


class InspectionIn(BaseModel):
    plan_id: int
    lot_id: int | None = None
    work_order_id: int | None = None
    gr_id: int | None = None
    quantity_inspected: Decimal = Decimal("0")
    measurements: list[MeasurementIn] = Field(min_length=1)
    notes: str | None = None


class InspectionOut(BaseModel):
    id: int
    plan_id: int
    stage: InspectionStage
    item_id: int | None
    lot_id: int | None
    work_order_id: int | None
    gr_id: int | None
    quantity_inspected: Decimal
    quantity_passed: Decimal
    quantity_failed: Decimal
    inspector_id: int | None
    inspected_at: datetime | None
    result: InspectionResult
    notes: str | None
    model_config = ConfigDict(from_attributes=True)


class DefectIn(BaseModel):
    inspection_id: int
    defect_type: str
    quantity: Decimal
    description: str | None = None
    action: str | None = None


# ---- Plans -----------------------------------------------------------------


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    stage: InspectionStage | None = None,
    item_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(InspectionPlan)
        .options(selectinload(InspectionPlan.criteria))
        .filter(InspectionPlan.is_active.is_(True))
        .order_by(InspectionPlan.code)
    )
    if stage:
        q = q.filter(InspectionPlan.stage == stage)
    if item_id is not None:
        q = q.filter(InspectionPlan.item_id == item_id)
    return q.all()


@router.post(
    "/plans",
    response_model=PlanOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_plan(payload: PlanIn, db: Session = Depends(get_db)):
    if db.query(InspectionPlan).filter(InspectionPlan.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    plan = InspectionPlan(
        code=payload.code, name=payload.name, item_id=payload.item_id,
        stage=payload.stage, notes=payload.notes,
    )
    for c in payload.criteria:
        if c.measurement_type not in ("numeric", "boolean", "text"):
            raise HTTPException(status_code=400, detail=f"Bad measurement_type {c.measurement_type}")
        plan.criteria.append(InspectionCriterion(**c.model_dump()))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ---- Inspections -----------------------------------------------------------


def _evaluate_measurement(crit: InspectionCriterion, m: MeasurementIn) -> bool:
    """Compare a measurement against its criterion. Returns True for pass."""
    if crit.measurement_type == "numeric":
        if m.numeric_value is None:
            return False
        v = Decimal(m.numeric_value)
        if crit.min_value is not None and v < Decimal(crit.min_value):
            return False
        if crit.max_value is not None and v > Decimal(crit.max_value):
            return False
        return True
    if crit.measurement_type == "boolean":
        return bool(m.boolean_value)
    if crit.measurement_type == "text":
        if crit.expected_text and m.text_value:
            return m.text_value.strip() == crit.expected_text.strip()
        return False
    return False


@router.get("/inspections", response_model=Page[InspectionOut])
def list_inspections(
    stage: InspectionStage | None = None,
    result: InspectionResult | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Inspection).order_by(Inspection.created_at.desc())
    if stage:
        q = q.filter(Inspection.stage == stage)
    if result:
        q = q.filter(Inspection.result == result)
    return paginate(q, params)


@router.post(
    "/inspections",
    response_model=InspectionOut,
    dependencies=[Depends(require_role("staff"))],
)
def submit_inspection(
    payload: InspectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = (
        db.query(InspectionPlan)
        .options(selectinload(InspectionPlan.criteria))
        .filter(InspectionPlan.id == payload.plan_id)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    crit_by_id = {c.id: c for c in plan.criteria}

    insp = Inspection(
        plan_id=plan.id, stage=plan.stage, item_id=plan.item_id,
        lot_id=payload.lot_id, work_order_id=payload.work_order_id,
        gr_id=payload.gr_id,
        quantity_inspected=payload.quantity_inspected,
        inspector_id=user.id, inspected_at=datetime.utcnow(),
        notes=payload.notes,
    )
    all_passed = True
    for m in payload.measurements:
        crit = crit_by_id.get(m.criterion_id)
        if not crit:
            raise HTTPException(
                status_code=400,
                detail=f"criterion_id {m.criterion_id} not on plan {plan.code}",
            )
        passed = _evaluate_measurement(crit, m)
        if not passed:
            all_passed = False
        insp.measurements.append(InspectionMeasurement(
            criterion_id=m.criterion_id,
            numeric_value=m.numeric_value,
            boolean_value=m.boolean_value,
            text_value=m.text_value,
            passed=passed,
        ))

    # Auto-result
    if all_passed:
        insp.result = InspectionResult.pass_
        insp.quantity_passed = payload.quantity_inspected
        insp.quantity_failed = Decimal("0")
    else:
        insp.result = InspectionResult.fail
        insp.quantity_passed = Decimal("0")
        insp.quantity_failed = payload.quantity_inspected

    db.add(insp)
    db.commit()
    db.refresh(insp)
    return insp


@router.post(
    "/inspections/{insp_id}/rework",
    response_model=InspectionOut,
    dependencies=[Depends(require_role("manager"))],
)
def mark_rework(insp_id: int, db: Session = Depends(get_db)):
    """Reclassify a failed inspection as rework-eligible (rather than scrap)."""
    insp = db.query(Inspection).filter(Inspection.id == insp_id).with_for_update().first()
    if not insp:
        raise HTTPException(status_code=404, detail="Not found")
    if insp.result != InspectionResult.fail:
        raise HTTPException(status_code=400, detail="Only failed inspections can be reworked")
    insp.result = InspectionResult.rework
    db.commit()
    db.refresh(insp)
    return insp


# ---- Defect log -----------------------------------------------------------


@router.get("/defects")
def list_defects(
    inspection_id: int | None = None,
    defect_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(DefectLog).order_by(DefectLog.reported_at.desc())
    if inspection_id is not None:
        q = q.filter(DefectLog.inspection_id == inspection_id)
    if defect_type:
        q = q.filter(DefectLog.defect_type == defect_type)
    return [
        {
            "id": d.id, "inspection_id": d.inspection_id,
            "defect_type": d.defect_type,
            "quantity": float(d.quantity), "description": d.description,
            "action": d.action, "reported_at": d.reported_at.isoformat(),
        }
        for d in q.all()
    ]


@router.post(
    "/defects",
    dependencies=[Depends(require_role("staff"))],
)
def record_defect(payload: DefectIn, db: Session = Depends(get_db)):
    if not db.query(Inspection).filter(Inspection.id == payload.inspection_id).first():
        raise HTTPException(status_code=404, detail="Inspection not found")
    if payload.action and payload.action not in ("rework", "scrap", "return"):
        raise HTTPException(status_code=400, detail="action must be rework|scrap|return")
    d = DefectLog(**payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id}


# ---- Analytics -------------------------------------------------------------


@router.get("/pass-rate")
def pass_rate(
    stage: InspectionStage | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Aggregate pass rate over the last `days`. Optionally per stage."""
    from datetime import timedelta
    from sqlalchemy import case as _sa_case

    cutoff = datetime.utcnow() - timedelta(days=days)
    q = db.query(
        Inspection.stage,
        func.count(Inspection.id).label("total"),
        func.coalesce(
            func.sum(
                _sa_case((Inspection.result == InspectionResult.pass_, 1), else_=0)
            ),
            0,
        ).label("passed"),
    ).filter(Inspection.created_at >= cutoff)
    if stage:
        q = q.filter(Inspection.stage == stage)
    rows = q.group_by(Inspection.stage).all()
    return {
        "window_days": days,
        "stages": [
            {
                "stage": r.stage.value,
                "total": int(r.total),
                "passed": int(r.passed),
                "pass_rate": round(int(r.passed) / max(int(r.total), 1), 3),
            }
            for r in rows
        ],
    }


@router.get("/defect-pareto")
def defect_pareto(days: int = 30, db: Session = Depends(get_db)):
    """Pareto (80/20) of defects by type."""
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(
            DefectLog.defect_type,
            func.count(DefectLog.id).label("n"),
            func.coalesce(func.sum(DefectLog.quantity), 0).label("qty"),
        )
        .filter(DefectLog.reported_at >= cutoff)
        .group_by(DefectLog.defect_type)
        .order_by(func.sum(DefectLog.quantity).desc())
        .all()
    )
    total_qty = sum(float(r.qty) for r in rows) or 1
    cum = 0.0
    out = []
    for r in rows:
        cum += float(r.qty)
        out.append({
            "defect_type": r.defect_type,
            "count": int(r.n),
            "quantity": float(r.qty),
            "cumulative_pct": round(cum / total_qty * 100, 1),
        })
    return {"window_days": days, "defects": out, "total_quantity": total_qty}
