from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class Role(str, PyEnum):
    """Application roles. Higher roles inherit lower-role permissions via require_role."""
    admin = "admin"      # full access (system, all modules)
    manager = "manager"  # can write in all business modules
    staff = "staff"      # can read all, write limited (e.g. own records)
    viewer = "viewer"    # read-only


class User(BaseEntity):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.staff, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin
