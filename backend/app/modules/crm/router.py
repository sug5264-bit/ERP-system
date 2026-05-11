"""CRM endpoints: Lead capture → Opportunity pipeline → won/lost analytics."""
from datetime import date, datetime
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


# ---- Campaigns + Segments -------------------------------------------------


import json as _json3
from datetime import datetime as _dt4

from app.modules.crm.models import (  # noqa: E402
    Campaign,
    CampaignSend,
    CampaignStatus,
    Segment,
)
from app.modules.sales.models import Customer  # noqa: E402


class SegmentIn(BaseModel):
    name: str
    description: str | None = None
    target_type: str = "lead"  # lead | customer
    criteria: dict = {}


class SegmentOut(BaseModel):
    id: int
    name: str
    description: str | None
    target_type: str
    criteria: dict
    model_config = ConfigDict(from_attributes=True)


def _seg_to_out(s: Segment) -> dict:
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "target_type": s.target_type,
        "criteria": _json3.loads(s.criteria) if s.criteria else {},
    }


@router.get("/segments", response_model=list[SegmentOut])
def list_segments(db: Session = Depends(get_db)):
    return [_seg_to_out(s) for s in db.query(Segment).order_by(Segment.name).all()]


@router.post("/segments", response_model=SegmentOut)
def create_segment(payload: SegmentIn, db: Session = Depends(get_db)):
    if payload.target_type not in ("lead", "customer"):
        raise HTTPException(status_code=400, detail="target_type must be lead|customer")
    s = Segment(
        name=payload.name, description=payload.description,
        target_type=payload.target_type,
        criteria=_json3.dumps(payload.criteria, ensure_ascii=False),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _seg_to_out(s)


def _resolve_segment(db: Session, segment: Segment) -> list[tuple[int | None, str]]:
    """Return (recipient_id, email) tuples that match the segment criteria."""
    crit = _json3.loads(segment.criteria) if segment.criteria else {}
    if segment.target_type == "customer":
        q = db.query(Customer)
        if "company" in crit:
            q = q.filter(Customer.company == crit["company"])
        rows = q.all()
        return [(c.id, c.email) for c in rows if c.email]
    else:
        q = db.query(Lead)
        if "status" in crit:
            q = q.filter(Lead.status == crit["status"])
        if "source" in crit:
            q = q.filter(Lead.source == crit["source"])
        rows = q.all()
        return [(l.id, l.email) for l in rows if l.email]


class CampaignIn(BaseModel):
    name: str
    segment_id: int
    channel: str = "email"
    subject: str | None = None
    body: str | None = None
    scheduled_at: datetime | None = None


class CampaignOut(BaseModel):
    id: int
    name: str
    segment_id: int
    channel: str
    subject: str | None
    body: str | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    status: CampaignStatus
    sent_count: int
    model_config = ConfigDict(from_attributes=True)


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(Campaign).order_by(Campaign.created_at.desc()).all()


@router.post("/campaigns", response_model=CampaignOut)
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db)):
    if not db.query(Segment).filter(Segment.id == payload.segment_id).first():
        raise HTTPException(status_code=404, detail="Segment not found")
    c = Campaign(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.post("/campaigns/{cid}/send", response_model=CampaignOut)
def send_campaign(cid: int, db: Session = Depends(get_db)):
    """Resolve segment → enqueue per-recipient sends (mock delivery).

    Production: hand off to an SMTP/SendGrid worker. Here we mark each
    CampaignSend as sent immediately for traceability and update counters.
    """
    c = db.query(Campaign).filter(Campaign.id == cid).with_for_update().first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    if c.status not in (CampaignStatus.draft, CampaignStatus.scheduled):
        raise HTTPException(status_code=400, detail=f"Cannot send from {c.status.value}")
    seg = db.query(Segment).filter(Segment.id == c.segment_id).first()
    recipients = _resolve_segment(db, seg)
    now = _dt4.utcnow()
    for rid, email in recipients:
        # Idempotent — skip if already sent for this campaign+email
        existing = (
            db.query(CampaignSend)
            .filter(
                CampaignSend.campaign_id == c.id,
                CampaignSend.recipient_email == email,
            )
            .first()
        )
        if existing:
            continue
        db.add(CampaignSend(
            campaign_id=c.id, recipient_email=email, recipient_id=rid,
            sent_at=now,
        ))
    db.flush()  # surface pending CampaignSend inserts before counting
    c.sent_count = (
        db.query(CampaignSend)
        .filter(CampaignSend.campaign_id == c.id)
        .count()
    )
    c.sent_at = now
    c.status = CampaignStatus.sent
    db.commit()
    db.refresh(c)
    return c


@router.get("/campaigns/{cid}/sends")
def list_campaign_sends(cid: int, db: Session = Depends(get_db)):
    rows = (
        db.query(CampaignSend)
        .filter(CampaignSend.campaign_id == cid)
        .order_by(CampaignSend.sent_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "recipient_email": s.recipient_email,
            "recipient_id": s.recipient_id,
            "sent_at": s.sent_at.isoformat() if s.sent_at else None,
            "opened_at": s.opened_at.isoformat() if s.opened_at else None,
            "clicked_at": s.clicked_at.isoformat() if s.clicked_at else None,
        }
        for s in rows
    ]


# ---- Drip Sequences -------------------------------------------------------


from app.modules.crm.models import (  # noqa: E402
    CampaignSequence,
    SequenceEnrollment,
    SequenceStatus,
    SequenceStep,
    TriggerType,
)


class StepIn(BaseModel):
    delay_days: int = 0
    subject: str
    body: str = ""


class SequenceIn(BaseModel):
    name: str
    description: str | None = None
    trigger: TriggerType = TriggerType.manual
    steps: list[StepIn] = []


class SequenceOut(BaseModel):
    id: int
    name: str
    description: str | None
    trigger: TriggerType
    status: SequenceStatus
    steps: list[dict]
    model_config = ConfigDict(from_attributes=True)


def _seq_to_out(s: CampaignSequence) -> dict:
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "trigger": s.trigger.value, "status": s.status.value,
        "steps": [
            {"id": st.id, "delay_days": st.delay_days,
             "subject": st.subject, "body": st.body}
            for st in s.steps
        ],
    }


@router.get("/sequences")
def list_sequences(db: Session = Depends(get_db)):
    from sqlalchemy.orm import selectinload as _sel

    return [
        _seq_to_out(s) for s in
        db.query(CampaignSequence).options(_sel(CampaignSequence.steps)).all()
    ]


@router.post("/sequences")
def create_sequence(payload: SequenceIn, db: Session = Depends(get_db)):
    s = CampaignSequence(
        name=payload.name, description=payload.description,
        trigger=payload.trigger,
    )
    for st in payload.steps:
        if st.delay_days < 0:
            raise HTTPException(status_code=400, detail="delay_days must be >= 0")
        s.steps.append(SequenceStep(**st.model_dump()))
    db.add(s)
    db.commit()
    db.refresh(s)
    return _seq_to_out(s)


@router.post("/sequences/{seq_id}/enroll")
def enroll(seq_id: int, email: str, lead_id: int | None = None,
             db: Session = Depends(get_db)):
    if not db.query(CampaignSequence).filter(CampaignSequence.id == seq_id).first():
        raise HTTPException(status_code=404, detail="Sequence not found")
    if (
        db.query(SequenceEnrollment)
        .filter(
            SequenceEnrollment.sequence_id == seq_id,
            SequenceEnrollment.recipient_email == email,
            SequenceEnrollment.completed_at.is_(None),
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Already enrolled")
    en = SequenceEnrollment(
        sequence_id=seq_id, recipient_email=email,
        recipient_lead_id=lead_id,
    )
    db.add(en)
    db.commit()
    db.refresh(en)
    return {"id": en.id, "started_at": en.started_at.isoformat()}


@router.post("/sequences/run-due")
def run_due_sequence_steps(db: Session = Depends(get_db)):
    """Cron entry: process pending steps. For each active enrollment, find
    the next step whose delay_days has elapsed and 'send' it (mock SMTP)."""
    from datetime import datetime as _dtnow
    from sqlalchemy.orm import selectinload as _sel

    now = _dtnow.utcnow()
    enrollments = (
        db.query(SequenceEnrollment)
        .filter(SequenceEnrollment.completed_at.is_(None))
        .all()
    )
    sent = 0
    completed = 0
    for en in enrollments:
        seq = (
            db.query(CampaignSequence)
            .options(_sel(CampaignSequence.steps))
            .filter(CampaignSequence.id == en.sequence_id)
            .first()
        )
        if not seq or seq.status != SequenceStatus.active:
            continue
        steps = list(seq.steps)
        elapsed = (now - en.started_at).total_seconds() / 86400
        # Find the next un-sent step whose delay has elapsed
        for idx, step in enumerate(steps):
            if idx <= en.last_step_index:
                continue
            if step.delay_days > elapsed:
                break
            # Mock send — production hands off to SMTP/Celery
            en.last_step_index = idx
            sent += 1
        if en.last_step_index >= len(steps) - 1:
            en.completed_at = now
            completed += 1
    db.commit()
    return {"sent_steps": sent, "completed_enrollments": completed,
             "active_enrollments": len(enrollments) - completed}
