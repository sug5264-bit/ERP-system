from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class Recipe(BaseEntity):
    """A finished-good recipe — what ingredients + quantities + yield + cost.

    Distinct from BOM: BOM is mechanical assembly; Recipe carries portion
    yield, allergen flags, and nutrition aggregations.
    """

    __tablename__ = "fnb_recipes"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    finished_item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False, index=True
    )
    portion_size_g: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("100")
    )
    yield_portions: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("1")
    )
    instructions: Mapped[str | None] = mapped_column(String(4000))
    allergens: Mapped[str | None] = mapped_column(String(500))  # comma-separated
    is_active: Mapped[bool] = mapped_column(default=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan",
    )


class RecipeIngredient(BaseEntity):
    __tablename__ = "fnb_recipe_ingredients"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("fnb_recipes.id"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False
    )
    quantity_g: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    waste_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )  # 손실률 (껍질/뼈/지방 제거 등)
    notes: Mapped[str | None] = mapped_column(String(500))

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


# ---- HACCP --------------------------------------------------------------


class CCPType(str, PyEnum):
    cooking = "cooking"          # 가열
    cooling = "cooling"          # 냉각
    storage = "storage"          # 보관 온도
    cross_contamination = "cross_contamination"  # 교차오염
    sanitation = "sanitation"    # 위생
    other = "other"


class HACCPPlan(BaseEntity):
    """A HACCP plan for a recipe/process. Lists Critical Control Points."""

    __tablename__ = "fnb_haccp_plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("fnb_recipes.id"))
    description: Mapped[str | None] = mapped_column(String(2000))
    is_active: Mapped[bool] = mapped_column(default=True)

    ccps: Mapped[list["CriticalControlPoint"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
        order_by="CriticalControlPoint.sequence",
    )


class CriticalControlPoint(BaseEntity):
    __tablename__ = "fnb_ccps"

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("fnb_haccp_plans.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=10)
    type: Mapped[CCPType] = mapped_column(Enum(CCPType), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    # Critical limit: a measurable threshold (e.g., 가열 ≥ 75℃ 15초)
    critical_limit_text: Mapped[str] = mapped_column(String(500), nullable=False)
    monitor_frequency: Mapped[str] = mapped_column(
        String(100), default="매 배치"
    )
    corrective_action: Mapped[str | None] = mapped_column(String(2000))

    plan: Mapped[HACCPPlan] = relationship(back_populates="ccps")


class HACCPLog(BaseEntity):
    """Per-monitoring-event log for a CCP — must record actual value + action
    taken if outside the critical limit."""

    __tablename__ = "fnb_haccp_logs"

    ccp_id: Mapped[int] = mapped_column(
        ForeignKey("fnb_ccps.id"), nullable=False, index=True
    )
    monitored_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    monitor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    measured_value: Mapped[str] = mapped_column(String(200), nullable=False)
    is_within_limit: Mapped[bool] = mapped_column(default=True)
    corrective_action_taken: Mapped[str | None] = mapped_column(String(2000))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inv_lots.id"))
