from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.base_model import BaseEntity


class LeadStatus(str, PyEnum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    disqualified = "disqualified"
    converted = "converted"  # → opportunity created


class OpportunityStage(str, PyEnum):
    prospecting = "prospecting"
    qualification = "qualification"
    proposal = "proposal"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class Lead(BaseEntity):
    __tablename__ = "crm_leads"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(100))  # e.g. "referral", "website"
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus), default=LeadStatus.new, nullable=False, index=True
    )
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    notes: Mapped[str | None] = mapped_column(String(2000))
    # Plain integer (no FK) to avoid a circular foreign-key with Opportunity.lead_id.
    converted_opportunity_id: Mapped[int | None] = mapped_column(Integer)


class Opportunity(BaseEntity):
    __tablename__ = "crm_opportunities"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales_customers.id"), index=True
    )
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("crm_leads.id"))
    stage: Mapped[OpportunityStage] = mapped_column(
        Enum(OpportunityStage), default=OpportunityStage.prospecting, nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    probability: Mapped[int] = mapped_column(default=10)  # 0-100 percent
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    notes: Mapped[str | None] = mapped_column(String(2000))

    history: Mapped[list["StageChange"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class StageChange(BaseEntity):
    """Audit trail of opportunity stage transitions (for win-rate analytics)."""

    __tablename__ = "crm_stage_changes"

    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("crm_opportunities.id"), nullable=False, index=True
    )
    from_stage: Mapped[OpportunityStage | None] = mapped_column(Enum(OpportunityStage))
    to_stage: Mapped[OpportunityStage] = mapped_column(Enum(OpportunityStage), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(String(500))

    opportunity: Mapped[Opportunity] = relationship(back_populates="history")


class CampaignStatus(str, PyEnum):
    draft = "draft"
    scheduled = "scheduled"
    sending = "sending"
    sent = "sent"
    cancelled = "cancelled"


class Segment(BaseEntity):
    """A saved customer/lead query — used to target campaigns."""

    __tablename__ = "crm_segments"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    target_type: Mapped[str] = mapped_column(String(20), default="lead")  # lead|customer
    # JSON criteria; e.g. {"status": "qualified", "source": "website"}
    criteria: Mapped[str] = mapped_column(String(2000), default="{}")


class Campaign(BaseEntity):
    """An outbound campaign (email/SMS) to a Segment."""

    __tablename__ = "crm_campaigns"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("crm_segments.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email|sms
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(String(8000))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus), default=CampaignStatus.draft, nullable=False, index=True
    )
    sent_count: Mapped[int] = mapped_column(default=0)


class CampaignSend(BaseEntity):
    """Per-recipient send record (idempotent)."""

    __tablename__ = "crm_campaign_sends"

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("crm_campaigns.id"), nullable=False, index=True
    )
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipient_id: Mapped[int | None] = mapped_column()  # lead_id or customer_id
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(String(500))


class TriggerType(str, PyEnum):
    lead_created = "lead_created"        # 리드 등록 시
    stage_changed = "stage_changed"       # opportunity 단계 변경
    manual = "manual"                     # 수동 등록


class SequenceStatus(str, PyEnum):
    active = "active"
    paused = "paused"
    archived = "archived"


class CampaignSequence(BaseEntity):
    """A drip campaign: multiple Steps fired off after a trigger event,
    spaced by delay_days. Example: trial day 0 / nudge day 3 / final day 7."""

    __tablename__ = "crm_sequences"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    trigger: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType), default=TriggerType.manual, nullable=False, index=True
    )
    status: Mapped[SequenceStatus] = mapped_column(
        Enum(SequenceStatus), default=SequenceStatus.active, nullable=False, index=True
    )

    steps: Mapped[list["SequenceStep"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan",
        order_by="SequenceStep.delay_days",
    )


class SequenceStep(BaseEntity):
    __tablename__ = "crm_sequence_steps"

    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("crm_sequences.id"), nullable=False, index=True
    )
    delay_days: Mapped[int] = mapped_column(default=0)  # days from enrollment
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(String(8000), default="")

    sequence: Mapped[CampaignSequence] = relationship(back_populates="steps")


class SequenceEnrollment(BaseEntity):
    """A specific recipient enrolled in a sequence. Each step is sent when
    elapsed_days >= step.delay_days."""

    __tablename__ = "crm_sequence_enrollments"

    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("crm_sequences.id"), nullable=False, index=True
    )
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipient_lead_id: Mapped[int | None] = mapped_column(ForeignKey("crm_leads.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_step_index: Mapped[int] = mapped_column(default=-1)  # -1 = not yet sent
