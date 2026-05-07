import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

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
    template_id: int | None = None
    form_data: dict | None = None


class ApprovalRequestOut(BaseModel):
    id: int
    title: str
    resource_type: str
    resource_id: int
    requester_id: int
    status: ApprovalStatus
    current_step: int
    created_at: datetime
    template_id: int | None = None
    form_data: dict | None = None
    steps: list[ApprovalStepOut]

    class Config:
        from_attributes = True

    @field_validator("form_data", mode="before")
    @classmethod
    def _decode_form_data(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v


class ApprovalDecision(BaseModel):
    comment: str | None = None


class FormFieldIn(BaseModel):
    key: str
    label: str
    type: str  # text | number | date | select | textarea | checkbox
    required: bool = False
    options: list[str] | None = None


class FormStepIn(BaseModel):
    order: int
    approver_id: int


class FormTemplateIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    schema_: list[FormFieldIn] = Field(default_factory=list, alias="schema")
    default_steps: list[FormStepIn] = Field(default_factory=list)
    is_active: bool = True

    model_config = {"populate_by_name": True}


class FormTemplateOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    schema_: list[FormFieldIn]
    default_steps: list[FormStepIn]
    is_active: bool
