from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.approvals.models import ApprovalStatus


class ApprovalStepIn(BaseModel):
    order: int
    approver_id: int


class ApprovalStepOut(BaseModel):
    id: int
    order: int
    approver_id: int
    status: ApprovalStatus
    comment: str | None
    decided_at: datetime | None

    class Config:
        from_attributes = True


class ApprovalRequestCreate(BaseModel):
    title: str
    resource_type: str
    resource_id: int
    steps: list[ApprovalStepIn] = Field(min_length=1)


class ApprovalRequestOut(BaseModel):
    id: int
    title: str
    resource_type: str
    resource_id: int
    requester_id: int
    status: ApprovalStatus
    current_step: int
    created_at: datetime
    steps: list[ApprovalStepOut]

    class Config:
        from_attributes = True


class ApprovalDecision(BaseModel):
    comment: str | None = None
