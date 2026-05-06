from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.approvals.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
)
from app.modules.approvals.schemas import ApprovalRequestCreate


def list_requests(
    db: Session,
    requester_id: int | None = None,
    approver_id: int | None = None,
    status: ApprovalStatus | None = None,
) -> list[ApprovalRequest]:
    q = db.query(ApprovalRequest)
    if requester_id is not None:
        q = q.filter(ApprovalRequest.requester_id == requester_id)
    if status is not None:
        q = q.filter(ApprovalRequest.status == status)
    if approver_id is not None:
        q = q.join(ApprovalStep).filter(ApprovalStep.approver_id == approver_id).distinct()
    return q.order_by(ApprovalRequest.created_at.desc()).all()


def get_request(db: Session, request_id: int) -> ApprovalRequest | None:
    return db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()


def create_request(db: Session, requester_id: int, payload: ApprovalRequestCreate) -> ApprovalRequest:
    sorted_steps = sorted(payload.steps, key=lambda s: s.order)
    req = ApprovalRequest(
        title=payload.title,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        requester_id=requester_id,
        status=ApprovalStatus.pending,
        current_step=sorted_steps[0].order,
    )
    for s in sorted_steps:
        req.steps.append(ApprovalStep(order=s.order, approver_id=s.approver_id))
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def decide(
    db: Session,
    request_id: int,
    user_id: int,
    approve: bool,
    comment: str | None = None,
) -> ApprovalRequest:
    # Lock the request row so concurrent approve/reject serialize.
    req = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not req:
        raise ValueError("Approval request not found")
    if req.status != ApprovalStatus.pending:
        raise ValueError(f"Request is already {req.status.value}")

    current = next(
        (s for s in req.steps if s.order == req.current_step and s.status == ApprovalStatus.pending),
        None,
    )
    if not current:
        raise ValueError("No pending step")
    if current.approver_id != user_id:
        raise ValueError("You are not the assigned approver for the current step")

    current.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    current.comment = comment
    current.decided_at = datetime.utcnow()

    if not approve:
        req.status = ApprovalStatus.rejected
    else:
        next_step = next(
            (s for s in req.steps if s.order > current.order and s.status == ApprovalStatus.pending),
            None,
        )
        if next_step:
            req.current_step = next_step.order
        else:
            req.status = ApprovalStatus.approved

    db.commit()
    db.refresh(req)
    return req


def cancel(db: Session, request_id: int, user_id: int) -> ApprovalRequest:
    req = get_request(db, request_id)
    if not req:
        raise ValueError("Approval request not found")
    if req.requester_id != user_id:
        raise ValueError("Only the requester can cancel")
    if req.status != ApprovalStatus.pending:
        raise ValueError(f"Cannot cancel a {req.status.value} request")
    req.status = ApprovalStatus.cancelled
    db.commit()
    db.refresh(req)
    return req
