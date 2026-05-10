from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class Dashboard(BaseEntity):
    __tablename__ = "dashboards"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    is_public: Mapped[bool] = mapped_column(default=False)

    widgets: Mapped[list["DashboardWidget"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )


class DashboardWidget(BaseEntity):
    __tablename__ = "dashboard_widgets"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "position", name="uq_widget_position"),
    )

    dashboard_id: Mapped[int] = mapped_column(
        ForeignKey("dashboards.id"), nullable=False, index=True
    )
    report_definition_id: Mapped[int] = mapped_column(
        ForeignKey("report_definitions.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    chart_type: Mapped[str] = mapped_column(String(20), default="table")  # table|bar|line|kpi

    dashboard: Mapped[Dashboard] = relationship(back_populates="widgets")
