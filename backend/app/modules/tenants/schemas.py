from pydantic import BaseModel, ConfigDict


class TenantBase(BaseModel):
    code: str
    name: str
    description: str | None = None


class TenantCreate(TenantBase):
    pass


class TenantOut(TenantBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserTenantAssign(BaseModel):
    user_id: int
    tenant_id: int
    is_default: bool = False
