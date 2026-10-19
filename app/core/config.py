from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-in-production-please-use-a-long-random-string"


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

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@cyberparts.dev"
    ADMIN_PASSWORD: str = "Admin123!"

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.ENVIRONMENT == "production" and self.SECRET_KEY == DEFAULT_SECRET_KEY:
            raise ValueError("SECRET_KEY debe configurarse con un valor propio en produccion")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
