from pydantic import BaseModel, Field

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
