from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    username: str = Field(description="Nombre de usuario o correo")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class OAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=16, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(
                f"La contrasena no puede superar {BCRYPT_MAX_BYTES} bytes en UTF-8"
            )
        return value


class OAuthAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    email: str
    linked_at: datetime = Field(validation_alias="created_at")


class OAuthAccountsRead(BaseModel):
    github: OAuthAccountRead | None = None


class OAuthLinkStartResponse(BaseModel):
    authorize_url: str
