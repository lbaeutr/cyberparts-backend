from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import RoleName


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(UserCreate):
    """Registro publico: siempre crea un CLIENTE."""


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    role: RoleName = Field(validation_alias="role_name")


class UserRoleUpdate(BaseModel):
    role: RoleName


class UserActiveUpdate(BaseModel):
    is_active: bool
