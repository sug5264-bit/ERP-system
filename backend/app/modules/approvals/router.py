from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.modules.approvals import service
from app.modules.approvals.models import ApprovalStatus
from app.modules.approvals.schemas import (
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalRequestOut,
)
from app.modules.auth.models import User

router = APIRouter(
    prefix="/api/approvals",
    tags=["approvals"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[ApprovalRequestOut])
def list_requests(
    scope: str = Query("all", pattern="^(all|mine|inbox)$"),
    status: ApprovalStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if scope == "mine":
        return service.list_requests(db, requester_id=current_user.id, status=status)
    if scope == "inbox":
        return service.list_requests(db, approver_id=current_user.id, status=status)
    return service.list_requests(db, status=status)


@router.post("", response_model=ApprovalRequestOut)
def create_request(
    payload: ApprovalRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = service.create_request(db, current_user.id, payload)

    # Fire-and-forget email to first approver, if SMTP configured.
    try:
        from app.core.email import send_email_safe

        first = req.steps[0]
        approver = db.query(User).filter(User.id == first.approver_id).first()
        if approver:
            send_email_safe(
                to=approver.email,
                subject=f"[ERP] 결재 요청: {req.title}",
                body=f"{current_user.full_name}님이 결재를 요청했습니다.\n\n제목: {req.title}\n리소스: {req.resource_type}#{req.resource_id}\n",
            )
    except Exception:
        pass

    return req


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
def approve(
    request_id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return service.decide(db, request_id, current_user.id, True, decision.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{request_id}/reject", response_model=ApprovalRequestOut)
def reject(
    request_id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return service.decide(db, request_id, current_user.id, False, decision.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{request_id}/cancel", response_model=ApprovalRequestOut)
def cancel(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return service.cancel(db, request_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
