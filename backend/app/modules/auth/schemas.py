from pydantic import BaseModel, EmailStr

from app.modules.auth.models import Role


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: Role = Role.staff


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
