import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", SECRET_KEY=DEFAULT_SECRET_KEY)


def test_production_accepts_custom_secret_key():
    settings = Settings(ENVIRONMENT="production", SECRET_KEY="x" * 64)

    assert settings.ENVIRONMENT == "production"


def test_development_allows_default_secret_key():
    settings = Settings(ENVIRONMENT="development", SECRET_KEY=DEFAULT_SECRET_KEY)

    assert settings.SECRET_KEY == DEFAULT_SECRET_KEY
