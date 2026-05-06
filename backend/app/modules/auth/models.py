from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    module_permissions: Mapped[list["UserModulePermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin


class UserModulePermission(BaseEntity):
    """Per-module override of a user's effective role.

    If a row exists for (user, module), it takes precedence over user.role
    when checking access to that module.
    """

    __tablename__ = "user_module_permissions"
    __table_args__ = (UniqueConstraint("user_id", "module", name="uq_user_module"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)

    user: Mapped[User] = relationship(back_populates="module_permissions")
