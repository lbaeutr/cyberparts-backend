from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.models.enums import RoleName


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _check_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(
                f"La contrasena no puede superar {BCRYPT_MAX_BYTES} bytes en UTF-8"
            )
        return value


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
