"""User-defined report definitions.

A `ReportDefinition` describes WHAT to query (data source, columns, filters,
aggregations) without users writing SQL. The runtime translates the JSON spec
into a safe SQLAlchemy query.
"""
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class ReportDefinition(BaseEntity):
    __tablename__ = "report_definitions"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    # JSON: {data_source, columns: [...], filters: [...], group_by: [...], order_by: [...]}
    spec: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
