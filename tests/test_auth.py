from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decode_access_token, verify_password
from app.main import app
from app.models.user import User

REGISTER_PAYLOAD = {
    "username": "newbie",
    "email": "newbie@test.dev",
    "password": "Secret123!",
}


def test_register_creates_cliente_with_hashed_password(client, db):
    response = client.post("/api/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["role"] == "CLIENTE"
    assert data["username"] == "newbie"
    assert "password" not in data
    assert "password_hash" not in data

    user = db.scalar(select(User).where(User.username == "newbie"))
    assert user is not None
    assert user.password_hash.startswith("$2b$")
    assert user.password_hash != REGISTER_PAYLOAD["password"]
    assert verify_password(REGISTER_PAYLOAD["password"], user.password_hash)


@pytest.mark.parametrize(
    "payload",
    [
        {**REGISTER_PAYLOAD, "email": "otro@test.dev"},
        {**REGISTER_PAYLOAD, "username": "otro"},
    ],
)
def test_register_duplicates_return_409(client, create_user, payload):
    create_user("newbie", password="Secret123!")

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {**REGISTER_PAYLOAD, "password": "corta"},
        {**REGISTER_PAYLOAD, "email": "no-es-email"},
        {**REGISTER_PAYLOAD, "username": "ab"},
    ],
)
def test_register_validation_errors(client, payload):
    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["username", "email"])
def test_login_accepts_username_or_email(client, create_user, field):
    user = create_user("trinity")

    response = client.post(
        "/api/auth/login",
        json={"username": getattr(user, field), "password": "Test1234!"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert data["user"]["username"] == "trinity"
    assert decode_access_token(data["access_token"])["role"] == "CLIENTE"


def test_login_sets_httponly_refresh_cookie(client, create_user):
    create_user("trinity")

    response = client.post(
        "/api/auth/login",
        json={"username": "trinity", "password": "Test1234!"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert settings.REFRESH_COOKIE_NAME in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_login_with_wrong_password_returns_401(client, create_user):
    create_user("trinity")

    response = client.post(
        "/api/auth/login",
        json={"username": "trinity", "password": "Incorrecta123!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"


def test_login_unknown_user_returns_401(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "nadie", "password": "Test1234!"},
    )

    assert response.status_code == 401


def test_login_inactive_user_returns_403(client, create_user):
    create_user("apoc", is_active=False)

    response = client.post(
        "/api/auth/login",
        json={"username": "apoc", "password": "Test1234!"},
    )

    assert response.status_code == 403


def test_me_returns_current_user(client, cliente_headers, cliente_user):
    response = client.get("/api/auth/me", headers=cliente_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == cliente_user.id
    assert data["role"] == "CLIENTE"


def test_me_without_token_returns_401(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer token-invalido"}
    )

    assert response.status_code == 401


def test_me_with_non_access_token_returns_401(client, cliente_user):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(cliente_user.id),
            "role": "CLIENTE",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_with_expired_token_returns_401(client, cliente_user):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(cliente_user.id),
            "role": "CLIENTE",
            "type": "access",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert "expirado" in response.json()["detail"]


def test_refresh_rotates_token_and_old_token_is_rejected(client, create_user):
    create_user("trinity")
    login = client.post(
        "/api/auth/login",
        json={"username": "trinity", "password": "Test1234!"},
    )
    assert login.status_code == 200
    old_token = client.cookies.get(settings.REFRESH_COOKIE_NAME)

    refresh = client.post("/api/auth/refresh")

    assert refresh.status_code == 200, refresh.text
    new_token = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert new_token and new_token != old_token
    assert refresh.json()["user"]["username"] == "trinity"

    stale_client = TestClient(app)
    replay = stale_client.post(
        "/api/auth/refresh", cookies={settings.REFRESH_COOKIE_NAME: old_token}
    )
    assert replay.status_code == 401


def test_refresh_without_cookie_returns_401(client):
    response = client.post("/api/auth/refresh")

    assert response.status_code == 401


def test_refresh_for_deactivated_user_returns_401(client, create_user, db):
    user = create_user("switch")
    client.post(
        "/api/auth/login",
        json={"username": "switch", "password": "Test1234!"},
    )

    user.is_active = False
    db.commit()

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401


def test_logout_revokes_refresh_token(client, create_user):
    create_user("trinity")
    client.post(
        "/api/auth/login",
        json={"username": "trinity", "password": "Test1234!"},
    )
    token = client.cookies.get(settings.REFRESH_COOKIE_NAME)

    logout = client.post("/api/auth/logout")

    assert logout.status_code == 204
    stale_client = TestClient(app)
    replay = stale_client.post(
        "/api/auth/refresh", cookies={settings.REFRESH_COOKIE_NAME: token}
    )
    assert replay.status_code == 401


def test_register_normalizes_email(client, db):
    payload = {**REGISTER_PAYLOAD, "email": "NewBie@Test.DEV"}

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["email"] == "newbie@test.dev"
    stored = db.scalar(select(User).where(User.username == "newbie"))
    assert stored is not None
    assert stored.email == "newbie@test.dev"

    login = client.post(
        "/api/auth/login",
        json={"username": "NEWBIE@TEST.DEV", "password": "Secret123!"},
    )
    assert login.status_code == 200, login.text


def test_register_accepts_password_at_bcrypt_limit(client):
    response = client.post(
        "/api/auth/register",
        json={**REGISTER_PAYLOAD, "password": "a" * 72},
    )

    assert response.status_code == 201, response.text


def test_register_rejects_password_over_bcrypt_limit(client):
    response = client.post(
        "/api/auth/register",
        json={**REGISTER_PAYLOAD, "password": "ñ" * 37},
    )

    assert response.status_code == 422
