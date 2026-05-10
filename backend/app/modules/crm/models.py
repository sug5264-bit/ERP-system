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
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("sales_customers.id"))
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
