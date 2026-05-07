from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class Role(str, PyEnum):
    """Application roles. Higher roles inherit lower-role permissions via require_role.

    `supplier` is an external role: a portal user that may only see/act on
    their own Supplier's purchase orders. They cannot access other modules.
    """
    admin = "admin"
    manager = "manager"
    staff = "staff"
    viewer = "viewer"
    supplier = "supplier"


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
    __tablename__ = "user_module_permissions"
    __table_args__ = (UniqueConstraint("user_id", "module", name="uq_user_module"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)

    user: Mapped[User] = relationship(back_populates="module_permissions")


class ApiKey(BaseEntity):
    __tablename__ = "api_keys"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_per_minute: Mapped[int] = mapped_column(Integer, default=60)


class RefreshToken(BaseEntity):
    """Server-side refresh token store. Lets us revoke individual sessions."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str | None] = mapped_column(String(500))
