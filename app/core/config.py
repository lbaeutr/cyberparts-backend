from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "CyberParts API"
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+psycopg://cyberparts:cyberparts@127.0.0.1:5432/cyberparts"

    SECRET_KEY: str = "change-me-in-production-please-use-a-long-random-string"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
