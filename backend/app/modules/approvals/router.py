from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.ws import manager as ws_manager
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

    try:
        from app.core.email import send_email_safe

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
        return service.cancel(db, request_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
