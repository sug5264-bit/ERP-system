"""Recipe cost analysis + HACCP plan/log endpoints."""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    get_current_user,
    require_role,
)
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.fnb.models import (
    CCPType,
    CriticalControlPoint,
    HACCPLog,
    HACCPPlan,
    Recipe,
    RecipeIngredient,
)
from app.modules.inventory.models import Item

router = APIRouter(
    prefix="/api/fnb",
    tags=["fnb"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Recipe schemas -------------------------------------------------------


class IngredientIn(BaseModel):
    item_id: int
    quantity_g: Decimal
    waste_pct: Decimal = Decimal("0")
    notes: str | None = None


class IngredientOut(IngredientIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RecipeIn(BaseModel):
    code: str
    name: str
    finished_item_id: int
    portion_size_g: Decimal = Decimal("100")
    yield_portions: Decimal = Decimal("1")
    instructions: str | None = None
    allergens: str | None = None
    ingredients: list[IngredientIn] = Field(min_length=1)


class RecipeOut(BaseModel):
    id: int
    code: str
    name: str
    finished_item_id: int
    portion_size_g: Decimal
    yield_portions: Decimal
    instructions: str | None
    allergens: str | None
    is_active: bool
    ingredients: list[IngredientOut]
    model_config = ConfigDict(from_attributes=True)


# ---- Recipe endpoints -----------------------------------------------------


@router.get("/recipes", response_model=list[RecipeOut])
def list_recipes(db: Session = Depends(get_db)):
    return (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.is_active.is_(True))
        .order_by(Recipe.code)
        .all()
    )


@router.post(
    "/recipes",
    response_model=RecipeOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_recipe(payload: RecipeIn, db: Session = Depends(get_db)):
    if db.query(Recipe).filter(Recipe.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code exists")
    if payload.yield_portions <= 0 or payload.portion_size_g <= 0:
        raise HTTPException(status_code=400, detail="portion_size_g and yield_portions must be > 0")
    r = Recipe(
        code=payload.code, name=payload.name,
        finished_item_id=payload.finished_item_id,
        portion_size_g=payload.portion_size_g,
        yield_portions=payload.yield_portions,
        instructions=payload.instructions, allergens=payload.allergens,
    )
    for ing in payload.ingredients:
        if ing.quantity_g <= 0:
            raise HTTPException(status_code=400, detail="ingredient quantity_g must be > 0")
        if ing.waste_pct < 0 or ing.waste_pct > 100:
            raise HTTPException(status_code=400, detail="waste_pct must be 0-100")
        r.ingredients.append(RecipeIngredient(**ing.model_dump()))
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("/recipes/{rid}/nutrition")
def recipe_nutrition(rid: int, db: Session = Depends(get_db)):
    """Aggregate nutrition per portion using each ingredient's per-100g facts.

    Ingredients without nutrition data are skipped and listed in `unknown`.
    """
    r = (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.id == rid)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    items = {
        it.id: it for it in db.query(Item).filter(
            Item.id.in_([i.item_id for i in r.ingredients])
        ).all()
    }
    totals = {"calories": Decimal("0"), "protein_g": Decimal("0"),
              "carbs_g": Decimal("0"), "fat_g": Decimal("0"),
              "sodium_mg": Decimal("0")}
    unknown: list[str] = []
    for ing in r.ingredients:
        it = items.get(ing.item_id)
        if not it:
            continue
        if it.calories_per_100g is None:
            unknown.append(it.sku)
            continue
        factor = Decimal(ing.quantity_g) / Decimal("100")
        totals["calories"] += Decimal(it.calories_per_100g or 0) * factor
        totals["protein_g"] += Decimal(it.protein_g_per_100g or 0) * factor
        totals["carbs_g"] += Decimal(it.carbs_g_per_100g or 0) * factor
        totals["fat_g"] += Decimal(it.fat_g_per_100g or 0) * factor
        totals["sodium_mg"] += Decimal(it.sodium_mg_per_100g or 0) * factor
    portions = Decimal(r.yield_portions) or Decimal("1")
    per_portion = {k: float((v / portions).quantize(Decimal("0.01")))
                    for k, v in totals.items()}
    return {
        "recipe_id": r.id, "code": r.code, "yield_portions": float(portions),
        "per_portion": per_portion,
        "unknown_ingredients": unknown,
    }


@router.get("/recipes/{rid}/cost")
def recipe_cost(rid: int, db: Session = Depends(get_db)):
    """Compute per-portion cost using each ingredient's item.unit_price.

    Cost per portion = sum(ingredient.quantity_g × (1 + waste_pct/100) ×
    item.unit_price) / yield_portions.

    Returns breakdown for transparency.
    """
    r = (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.id == rid)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")

    item_ids = [i.item_id for i in r.ingredients]
    items = {
        it.id: it for it in db.query(Item).filter(Item.id.in_(item_ids)).all()
    }
    total = Decimal("0")
    breakdown = []
    for ing in r.ingredients:
        it = items.get(ing.item_id)
        if not it:
            continue
        effective_g = Decimal(ing.quantity_g) * (
            Decimal("1") + Decimal(ing.waste_pct) / Decimal("100")
        )
        # Assume unit_price is per "EA" (whole item) — for F&B we treat
        # it as price per kg as a simplification. Production should track unit.
        cost = (effective_g / Decimal("1000")) * Decimal(it.unit_price)
        cost = cost.quantize(Decimal("0.01"))
        total += cost
        breakdown.append({
            "item_id": it.id, "sku": it.sku, "name": it.name,
            "quantity_g": float(ing.quantity_g),
            "waste_pct": float(ing.waste_pct),
            "effective_g": float(effective_g.quantize(Decimal("0.01"))),
            "unit_price_per_kg": float(it.unit_price),
            "cost": float(cost),
        })

    portions = Decimal(r.yield_portions)
    return {
        "recipe_id": r.id, "code": r.code, "name": r.name,
        "yield_portions": float(portions),
        "total_cost": float(total),
        "cost_per_portion": float((total / portions).quantize(Decimal("0.01"))) if portions > 0 else 0,
        "ingredients": breakdown,
    }


# ---- HACCP schemas --------------------------------------------------------


class CCPIn(BaseModel):
    sequence: int = 10
    type: CCPType
    description: str
    critical_limit_text: str
    monitor_frequency: str = "매 배치"
    corrective_action: str | None = None


class HACCPPlanIn(BaseModel):
    code: str
    title: str
    recipe_id: int | None = None
    description: str | None = None
    ccps: list[CCPIn] = Field(min_length=1)


class CCPOut(CCPIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class HACCPPlanOut(BaseModel):
    id: int
    code: str
    title: str
    recipe_id: int | None
    description: str | None
    is_active: bool
    ccps: list[CCPOut]
    model_config = ConfigDict(from_attributes=True)


class HACCPLogIn(BaseModel):
    ccp_id: int
    measured_value: str
    is_within_limit: bool
    corrective_action_taken: str | None = None
    lot_id: int | None = None


# ---- HACCP endpoints ------------------------------------------------------


@router.get("/haccp/plans", response_model=list[HACCPPlanOut])
def list_haccp_plans(db: Session = Depends(get_db)):
    return (
        db.query(HACCPPlan)
        .options(selectinload(HACCPPlan.ccps))
        .filter(HACCPPlan.is_active.is_(True))
        .order_by(HACCPPlan.code)
        .all()
    )


@router.post(
    "/haccp/plans",
    response_model=HACCPPlanOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_haccp_plan(payload: HACCPPlanIn, db: Session = Depends(get_db)):
    if db.query(HACCPPlan).filter(HACCPPlan.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code exists")
    plan = HACCPPlan(
        code=payload.code, title=payload.title,
        recipe_id=payload.recipe_id, description=payload.description,
    )
    for c in payload.ccps:
        plan.ccps.append(CriticalControlPoint(**c.model_dump()))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/haccp/logs")
def record_haccp_log(
    payload: HACCPLogIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.query(CriticalControlPoint).filter(
        CriticalControlPoint.id == payload.ccp_id
    ).first():
        raise HTTPException(status_code=404, detail="CCP not found")
    if not payload.is_within_limit and not payload.corrective_action_taken:
        raise HTTPException(
            status_code=400,
            detail="corrective_action_taken is required when out of limit",
        )
    log = HACCPLog(
        ccp_id=payload.ccp_id,
        monitor_id=user.id,
        measured_value=payload.measured_value,
        is_within_limit=payload.is_within_limit,
        corrective_action_taken=payload.corrective_action_taken,
        lot_id=payload.lot_id,
    )
    db.add(log)
    db.commit()

    # Auto-alert on violation — best-effort multi-channel
    if not payload.is_within_limit:
        try:
            from app.modules.notifications.channels import EmailAdapter, SlackAdapter

            ccp = db.query(CriticalControlPoint).filter(
                CriticalControlPoint.id == payload.ccp_id
            ).first()
            subject = f"[HACCP 위반] {ccp.type.value if ccp else 'CCP'} 한계기준 초과"
            body = (
                f"CCP: {ccp.description if ccp else payload.ccp_id}\n"
                f"한계기준: {ccp.critical_limit_text if ccp else '-'}\n"
                f"측정값: {payload.measured_value}\n"
                f"시정조치: {payload.corrective_action_taken}\n"
                f"기록자: {user.email} @ {log.monitored_at.isoformat()}"
            )
            SlackAdapter().send(subject, body)
            # Email goes to a configured QA mailing list (from env). Skip when
            # not configured.
            import os
            qa_list = os.environ.get("QA_ALERT_EMAILS", "")
            recipients = [e.strip() for e in qa_list.split(",") if e.strip()]
            if recipients:
                EmailAdapter().send(subject, body, recipients)
        except Exception:
            import logging
            logging.getLogger("erp.fnb").exception("HACCP alert dispatch failed")

    return {"id": log.id, "monitored_at": log.monitored_at.isoformat(),
             "alerted": not payload.is_within_limit}


@router.get("/haccp/logs")
def list_haccp_logs(
    ccp_id: int | None = None,
    only_violations: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(HACCPLog).order_by(HACCPLog.monitored_at.desc())
    if ccp_id is not None:
        q = q.filter(HACCPLog.ccp_id == ccp_id)
    if only_violations:
        q = q.filter(HACCPLog.is_within_limit.is_(False))
    rows = q.limit(500).all()
    return [
        {
            "id": r.id, "ccp_id": r.ccp_id,
            "monitored_at": r.monitored_at.isoformat(),
            "monitor_id": r.monitor_id,
            "measured_value": r.measured_value,
            "is_within_limit": r.is_within_limit,
            "corrective_action_taken": r.corrective_action_taken,
            "lot_id": r.lot_id,
        }
        for r in rows
    ]
