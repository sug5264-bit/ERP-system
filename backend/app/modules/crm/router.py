"""CRM endpoints: Lead capture → Opportunity pipeline → won/lost analytics."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import (
    get_current_internal_user,
    get_current_user,
    require_module_role,
)
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.auth.models import User
from app.modules.crm.models import (
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    StageChange,
)

router = APIRouter(
    prefix="/api/crm",
    tags=["crm"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class LeadIn(BaseModel):
    name: str
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    assigned_to_id: int | None = None
    notes: str | None = None


class LeadOut(LeadIn):
    id: int
    status: LeadStatus
    converted_opportunity_id: int | None
    model_config = ConfigDict(from_attributes=True)


class OpportunityIn(BaseModel):
    name: str
    customer_id: int | None = None
    lead_id: int | None = None
    stage: OpportunityStage = OpportunityStage.prospecting
    amount: Decimal = Decimal("0")
    probability: int = 10
    expected_close_date: date | None = None
    assigned_to_id: int | None = None
    notes: str | None = None


class OpportunityOut(OpportunityIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class StageChangeIn(BaseModel):
    to_stage: OpportunityStage
    comment: str | None = None


# ---- Lead endpoints --------------------------------------------------------


@router.get("/leads", response_model=Page[LeadOut])
def list_leads(
    status: LeadStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Lead).order_by(Lead.created_at.desc())
    if status:
        q = q.filter(Lead.status == status)
    return paginate(q, params)


@router.post(
    "/leads",
    response_model=LeadOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_lead(payload: LeadIn, db: Session = Depends(get_db)):
    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.patch(
    "/leads/{lead_id}",
    response_model=LeadOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def update_lead(lead_id: int, payload: LeadIn, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(lead, k, v)
    db.commit()
    db.refresh(lead)
    return lead


@router.post(
    "/leads/{lead_id}/convert",
    response_model=OpportunityOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def convert_lead(
    lead_id: int,
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Convert a Lead → Opportunity. Optionally bind to an existing Customer.

    Lead status moves to `converted` and links the new opportunity_id.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).with_for_update().first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    if lead.status == LeadStatus.converted:
        raise HTTPException(status_code=400, detail="Already converted")
    opp = Opportunity(
        name=f"{lead.company or lead.name}",
        customer_id=customer_id,
        lead_id=lead.id,
        assigned_to_id=lead.assigned_to_id or user.id,
    )
    db.add(opp)
    db.flush()
    # Initial stage history
    db.add(
        StageChange(
            opportunity_id=opp.id,
            from_stage=None,
            to_stage=OpportunityStage.prospecting,
            changed_by_id=user.id,
            comment="Converted from lead",
        )
    )
    lead.status = LeadStatus.converted
    lead.converted_opportunity_id = opp.id
    db.commit()
    db.refresh(opp)
    return opp


# ---- Opportunity endpoints -------------------------------------------------


@router.get("/opportunities", response_model=Page[OpportunityOut])
def list_opportunities(
    stage: OpportunityStage | None = None,
    assigned_to_id: int | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Opportunity).order_by(Opportunity.created_at.desc())
    if stage:
        q = q.filter(Opportunity.stage == stage)
    if assigned_to_id is not None:
        q = q.filter(Opportunity.assigned_to_id == assigned_to_id)
    return paginate(q, params)


@router.post(
    "/opportunities",
    response_model=OpportunityOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_opportunity(
    payload: OpportunityIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.probability < 0 or payload.probability > 100:
        raise HTTPException(status_code=400, detail="probability must be 0-100")
    opp = Opportunity(**payload.model_dump())
    db.add(opp)
    db.flush()
    db.add(
        StageChange(
            opportunity_id=opp.id,
            from_stage=None,
            to_stage=opp.stage,
            changed_by_id=user.id,
            comment="Created",
        )
    )
    db.commit()
    db.refresh(opp)
    return opp


@router.post(
    "/opportunities/{opp_id}/stage",
    response_model=OpportunityOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def change_stage(
    opp_id: int,
    payload: StageChangeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    opp = (
        db.query(Opportunity)
        .filter(Opportunity.id == opp_id)
        .with_for_update()
        .first()
    )
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    if opp.stage == payload.to_stage:
        return opp
    db.add(
        StageChange(
            opportunity_id=opp.id,
            from_stage=opp.stage,
            to_stage=payload.to_stage,
            changed_by_id=user.id,
            comment=payload.comment,
        )
    )
    opp.stage = payload.to_stage
    # Auto-update probability for terminal stages
    if payload.to_stage == OpportunityStage.won:
        opp.probability = 100
    elif payload.to_stage == OpportunityStage.lost:
        opp.probability = 0
    db.commit()
    db.refresh(opp)
    return opp


# ---- Pipeline summary ------------------------------------------------------


@router.get("/pipeline/summary")
def pipeline_summary(
    assigned_to_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Counts and weighted amount per stage. Foundation of any sales dashboard."""
    q = db.query(
        Opportunity.stage,
        func.count(Opportunity.id).label("count"),
        func.coalesce(func.sum(Opportunity.amount), 0).label("total_amount"),
        func.coalesce(
            func.sum(Opportunity.amount * Opportunity.probability / 100), 0
        ).label("weighted_amount"),
    )
    if assigned_to_id is not None:
        q = q.filter(Opportunity.assigned_to_id == assigned_to_id)
    rows = q.group_by(Opportunity.stage).all()
    return {
        "stages": [
            {
                "stage": r.stage.value,
                "count": int(r.count),
                "total_amount": float(r.total_amount),
                "weighted_amount": float(r.weighted_amount),
            }
            for r in rows
        ]
    }
