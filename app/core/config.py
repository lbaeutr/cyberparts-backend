from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-in-production-please-use-a-long-random-string"
DEFAULT_ADMIN_PASSWORD = "Admin123!"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "CyberParts API"
    API_PREFIX: str = "/api"
    ENVIRONMENT: Literal["development", "production", "test"] = "development"

    DATABASE_URL: str = "postgresql+psycopg://cyberparts:cyberparts@127.0.0.1:5432/cyberparts"

    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_REUSE_GRACE_SECONDS: int = 60

    RATE_LIMIT_ENABLED: bool = True

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@cyberparts.dev"
    ADMIN_PASSWORD: str = DEFAULT_ADMIN_PASSWORD

    SEED_DEMO_USERS: bool = False

    FRONTEND_URL: str = "http://localhost:5173"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/auth/oauth/github/callback"
    GITHUB_OAUTH_SCOPES: str = "read:user user:email"
    OAUTH_STATE_COOKIE_NAME: str = "oauth_state"
    OAUTH_STATE_TTL_SECONDS: int = 600
    OAUTH_EXCHANGE_TTL_SECONDS: int = 60

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET)

    @property
    def frontend_base_url(self) -> str:
        return self.FRONTEND_URL.rstrip("/")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == DEFAULT_SECRET_KEY:
                raise ValueError("SECRET_KEY debe configurarse con un valor propio en produccion")
            if self.ADMIN_PASSWORD == DEFAULT_ADMIN_PASSWORD:
                raise ValueError("ADMIN_PASSWORD debe cambiarse en produccion")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
