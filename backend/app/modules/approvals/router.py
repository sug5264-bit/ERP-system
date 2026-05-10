import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_role
from app.core.db import get_db
from app.core.ws import manager as ws_manager
from app.modules.approvals import service
from app.modules.approvals.models import ApprovalFormTemplate, ApprovalStatus
from app.modules.approvals.schemas import (
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalRequestOut,
    FormTemplateIn,
    FormTemplateOut,
)
from app.modules.auth.models import User




def _template_to_out(t: ApprovalFormTemplate) -> dict:
    return {
        "id": t.id,
        "code": t.code,
        "name": t.name,
        "description": t.description,
        "schema_": json.loads(t.schema or "[]"),
        "default_steps": json.loads(t.default_steps or "[]"),
        "is_active": t.is_active,
    }

router = APIRouter(
    prefix="/api/approvals",
    tags=["approvals"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("", response_model=list[ApprovalRequestOut])
def list_requests(
    scope: str = Query("all", pattern="^(all|mine|inbox)$"),
    status: ApprovalStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if scope == "mine":
        rows = service.list_requests(db, requester_id=current_user.id, status=status)
    elif scope == "inbox":
        rows = service.list_requests(db, approver_id=current_user.id, status=status)
    else:
        rows = service.list_requests(db, status=status)
    return rows


@router.post("", response_model=ApprovalRequestOut)
def create_request(
    payload: ApprovalRequestCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = service.create_request(db, current_user.id, payload)

    first = req.steps[0]
    ws_manager.emit(
        first.approver_id,
        {
            "type": "approval.requested",
            "request_id": req.id,
            "title": req.title,
            "requester": current_user.full_name,
        },
    )

    from app.core.email import queue_email

    approver = db.query(User).filter(User.id == first.approver_id).first()
    if approver:
        queue_email(
            background_tasks,
            to=approver.email,
            subject=f"[ERP] 결재 요청: {req.title}",
            body=(
                f"{current_user.full_name}님이 결재를 요청했습니다.\n\n"
                f"제목: {req.title}\n리소스: {req.resource_type}#{req.resource_id}\n"
            ),
        )

    return req


def _notify_decision(req, action: str, current_user) -> None:
    ws_manager.emit(
        req.requester_id,
        {
            "type": f"approval.{action}",
            "request_id": req.id,
            "title": req.title,
            "by": current_user.full_name,
            "status": req.status.value if hasattr(req.status, "value") else str(req.status),
        },
    )
    if req.status == ApprovalStatus.pending:
        next_step = next(
            (s for s in req.steps if s.order == req.current_step and s.status == ApprovalStatus.pending),
            None,
        )
        if next_step:
            ws_manager.emit(
                next_step.approver_id,
                {
                    "type": "approval.requested",
                    "request_id": req.id,
                    "title": req.title,
                    "requester": current_user.full_name,
                },
            )


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
def approve(
    request_id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        req = service.decide(db, request_id, current_user.id, True, decision.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _notify_decision(req, "approved", current_user)
    return req


@router.post("/{request_id}/reject", response_model=ApprovalRequestOut)
def reject(
    request_id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        req = service.decide(db, request_id, current_user.id, False, decision.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _notify_decision(req, "rejected", current_user)
    return req


@router.post("/{request_id}/cancel", response_model=ApprovalRequestOut)
def cancel(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        req = service.cancel(db, request_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return req


# ---- Form templates --------------------------------------------------------


@router.get("/templates", response_model=list[FormTemplateOut])
def list_templates(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(ApprovalFormTemplate)
    if active_only:
        q = q.filter(ApprovalFormTemplate.is_active.is_(True))
    return [_template_to_out(t) for t in q.order_by(ApprovalFormTemplate.code).all()]


@router.post(
    "/templates",
    response_model=FormTemplateOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_template(payload: FormTemplateIn, db: Session = Depends(get_db)):
    if db.query(ApprovalFormTemplate).filter(ApprovalFormTemplate.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    t = ApprovalFormTemplate(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        schema=json.dumps([f.model_dump() for f in payload.schema_], ensure_ascii=False),
        default_steps=json.dumps([s.model_dump() for s in payload.default_steps]),
        is_active=payload.is_active,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _template_to_out(t)


@router.put(
    "/templates/{template_id}",
    response_model=FormTemplateOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_template(
    template_id: int, payload: FormTemplateIn, db: Session = Depends(get_db)
):
    t = (
        db.query(ApprovalFormTemplate)
        .filter(ApprovalFormTemplate.id == template_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    t.name = payload.name
    t.description = payload.description
    t.schema = json.dumps([f.model_dump() for f in payload.schema_], ensure_ascii=False)
    t.default_steps = json.dumps([s.model_dump() for s in payload.default_steps])
    t.is_active = payload.is_active
    db.commit()
    db.refresh(t)
    return _template_to_out(t)


@router.delete(
    "/templates/{template_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    t = (
        db.query(ApprovalFormTemplate)
        .filter(ApprovalFormTemplate.id == template_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ---- SLA + delegation ------------------------------------------------------


from datetime import datetime as _dt3, timedelta as _td3  # noqa: E402

from pydantic import BaseModel as _BMd, ConfigDict as _Cfgd  # noqa: E402

from app.modules.approvals.models import ApprovalStep, UserDelegation  # noqa: E402


class DelegationIn(_BMd):
    delegate_id: int
    starts_at: _dt3
    ends_at: _dt3
    note: str | None = None


class DelegationOut(DelegationIn):
    id: int
    user_id: int
    model_config = _Cfgd(from_attributes=True)


def active_delegate_for(db: Session, user_id: int) -> int | None:
    """Returns the id of the current delegate for `user_id`, or None."""
    now = _dt3.utcnow()
    row = (
        db.query(UserDelegation)
        .filter(
            UserDelegation.user_id == user_id,
            UserDelegation.starts_at <= now,
            UserDelegation.ends_at >= now,
        )
        .order_by(UserDelegation.starts_at.desc())
        .first()
    )
    return row.delegate_id if row else None


@router.get("/delegations", response_model=list[DelegationOut])
def list_my_delegations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(UserDelegation)
        .filter(UserDelegation.user_id == user.id)
        .order_by(UserDelegation.starts_at.desc())
        .all()
    )


@router.post("/delegations", response_model=DelegationOut)
def create_delegation(
    payload: DelegationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    if payload.delegate_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delegate to yourself")
    d = UserDelegation(
        user_id=user.id,
        delegate_id=payload.delegate_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        note=payload.note,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/delegations/{did}")
def delete_delegation(
    did: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d = (
        db.query(UserDelegation)
        .filter(UserDelegation.id == did, UserDelegation.user_id == user.id)
        .first()
    )
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.post(
    "/steps/{step_id}/escalate",
)
def escalate_step(
    step_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move an overdue (or any pending) step to its escalate_to_id assignee.

    Allowed for: the original approver, the escalate_to_id, or admin.
    """
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    step = (
        db.query(ApprovalStep)
        .filter(ApprovalStep.id == step_id)
        .with_for_update()
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    if step.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Already {step.status.value}")
    if not step.escalate_to_id:
        raise HTTPException(status_code=400, detail="No escalate_to_id configured")
    if user.id not in (step.approver_id, step.escalate_to_id) and role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    step.approver_id = step.escalate_to_id
    step.escalated_at = _dt3.utcnow()
    db.commit()
    db.refresh(step)
    return {
        "id": step.id,
        "approver_id": step.approver_id,
        "escalated_at": step.escalated_at.isoformat(),
    }


@router.post(
    "/escalate-overdue",
    dependencies=[Depends(require_role("admin"))],
)
def escalate_overdue(db: Session = Depends(get_db)):
    """Cron entry-point: escalate every pending step past its due_at to the
    configured escalate_to_id. Idempotent — already-escalated steps are
    skipped via escalated_at."""
    now = _dt3.utcnow()
    overdue = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.status == ApprovalStatus.pending,
            ApprovalStep.due_at.is_not(None),
            ApprovalStep.due_at <= now,
            ApprovalStep.escalate_to_id.is_not(None),
            ApprovalStep.escalated_at.is_(None),
        )
        .all()
    )
    moved = 0
    for s in overdue:
        s.approver_id = s.escalate_to_id
        s.escalated_at = now
        moved += 1
    db.commit()
    return {"escalated": moved, "checked_at": now.isoformat()}
