import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_ADMIN_PASSWORD, DEFAULT_SECRET_KEY, Settings

CUSTOM_SECRET_KEY = "x" * 64
CUSTOM_ADMIN_PASSWORD = "ProdAdmin123!"


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY=DEFAULT_SECRET_KEY,
            ADMIN_PASSWORD=CUSTOM_ADMIN_PASSWORD,
        )


def test_production_rejects_default_admin_password():
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY=CUSTOM_SECRET_KEY,
            ADMIN_PASSWORD=DEFAULT_ADMIN_PASSWORD,
        )


def test_production_accepts_custom_secrets():
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY=CUSTOM_SECRET_KEY,
        ADMIN_PASSWORD=CUSTOM_ADMIN_PASSWORD,
    )

    assert settings.ENVIRONMENT == "production"


def test_development_allows_default_secrets():
    settings = Settings(
        ENVIRONMENT="development",
        SECRET_KEY=DEFAULT_SECRET_KEY,
        ADMIN_PASSWORD=DEFAULT_ADMIN_PASSWORD,
    )

    assert settings.SECRET_KEY == DEFAULT_SECRET_KEY


@pytest.mark.parametrize(
    ("raw_url", "expected_url"),
    [
        (
            "postgres://user:pass@host:5432/db?sslmode=require",
            "postgresql+psycopg://user:pass@host:5432/db?sslmode=require",
        ),
        (
            "postgresql://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
        (
            "postgresql+psycopg://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
    ],
)
def test_database_url_is_normalized(raw_url, expected_url):
    settings = Settings(DATABASE_URL=raw_url)

    assert settings.DATABASE_URL == expected_url


def test_seed_demo_users_defaults_to_false():
    assert Settings(_env_file=None).SEED_DEMO_USERS is False


def test_github_oauth_requires_client_id_and_secret():
    assert Settings(GITHUB_CLIENT_ID="id", GITHUB_CLIENT_SECRET="").github_oauth_configured is False
    assert Settings(GITHUB_CLIENT_ID="", GITHUB_CLIENT_SECRET="secret").github_oauth_configured is False
    assert Settings(GITHUB_CLIENT_ID="id", GITHUB_CLIENT_SECRET="secret").github_oauth_configured is True


def test_frontend_base_url_has_no_trailing_slash():
    settings = Settings(FRONTEND_URL="http://frontend.test/")

    assert settings.frontend_base_url == "http://frontend.test"
