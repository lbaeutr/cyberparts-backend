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


def test_github_oauth_requires_client_id_and_secret():
    assert Settings(GITHUB_CLIENT_ID="id", GITHUB_CLIENT_SECRET="").github_oauth_configured is False
    assert Settings(GITHUB_CLIENT_ID="", GITHUB_CLIENT_SECRET="secret").github_oauth_configured is False
    assert Settings(GITHUB_CLIENT_ID="id", GITHUB_CLIENT_SECRET="secret").github_oauth_configured is True


def test_frontend_base_url_has_no_trailing_slash():
    settings = Settings(FRONTEND_URL="http://frontend.test/")

    assert settings.frontend_base_url == "http://frontend.test"
