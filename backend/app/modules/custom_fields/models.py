from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class FieldType(str, PyEnum):
    text = "text"
    number = "number"
    date = "date"
    boolean = "boolean"
    select = "select"


class FieldDefinition(BaseEntity):
    """A custom field attached to a given entity type, e.g. ('item', 'origin_country')."""

    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint("entity_type", "key", name="uq_custom_field_entity_key"),
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[FieldType] = mapped_column(Enum(FieldType), nullable=False)
    options: Mapped[str | None] = mapped_column(Text)  # JSON-encoded list for select
    required: Mapped[bool] = mapped_column(Boolean, default=False)


class FieldValue(BaseEntity):
    """A value of a custom field for a specific entity row."""

    __tablename__ = "custom_field_values"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "field_id", name="uq_field_value_unique"
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    field_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text)
