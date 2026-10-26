import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
import respx
from sqlalchemy import select

from app.core.config import settings
from app.models.oauth import OAuthAccount, OAuthExchangeCode
from app.models.user import User
from app.services import oauth_service

GITHUB_ID = 123456
GITHUB_LOGIN = "octocat"
GITHUB_EMAIL = "octocat@example.com"


def _start(client):
    response = client.get("/api/auth/oauth/github/start", follow_redirects=False)
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    params = parse_qs(urlparse(location).query)
    return response, params, client.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)


def _callback(client, state: str, code: str | None = "github-code"):
    params = {"state": state}
    if code is not None:
        params["code"] = code
    return client.get(
        "/api/auth/oauth/github/callback",
        params=params,
        follow_redirects=False,
    )


def _redirect_params(response) -> dict[str, list[str]]:
    return parse_qs(urlparse(response.headers["location"]).query)


def _mock_github(
    account_id: int = GITHUB_ID,
    login: str = GITHUB_LOGIN,
    email: str = GITHUB_EMAIL,
    emails: list[dict] | None = None,
) -> None:
    respx.post(oauth_service.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "github-access-token",
                "token_type": "bearer",
                "scope": "read:user,user:email",
            },
        )
    )
    respx.get(oauth_service.GITHUB_USER_URL).mock(
        return_value=httpx.Response(200, json={"id": account_id, "login": login})
    )
    if emails is None:
        emails = [{"email": email, "primary": True, "verified": True}]
    respx.get(oauth_service.GITHUB_EMAILS_URL).mock(
        return_value=httpx.Response(200, json=emails)
    )


def _login_with_github(client, db) -> User:
    _mock_github()
    _, params, _ = _start(client)
    response = _callback(client, params["state"][0])
    assert response.status_code == 302
    db.expire_all()
    user = db.scalar(select(User).where(User.email == GITHUB_EMAIL))
    assert user is not None
    return user


def test_start_redirects_to_github_with_pkce_and_state_cookie(client):
    response, params, state_cookie = _start(client)

    assert params["client_id"] == [settings.GITHUB_CLIENT_ID]
    assert params["redirect_uri"] == [settings.GITHUB_REDIRECT_URI]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["code_challenge"][0]) == 43
    assert params["state"][0]
    assert state_cookie

    payload = jwt.decode(
        state_cookie, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    assert payload["type"] == "oauth_state"
    assert payload["mode"] == "login"
    assert payload["nonce"] == params["state"][0]
    digest = hashlib.sha256(payload["verifier"].encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    assert params["code_challenge"][0] == expected

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert f"path={settings.API_PREFIX}/auth/oauth" in cookie


def test_start_without_configuration_returns_frontend_error(client, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "")

    response = client.get("/api/auth/oauth/github/start", follow_redirects=False)

    assert response.status_code == 302
    assert _redirect_params(response)["error"] == ["not_configured"]


@respx.mock
def test_callback_creates_cliente_and_exchanges_code(client, db):
    _mock_github()
    _, params, _ = _start(client)

    response = _callback(client, params["state"][0])

    assert response.status_code == 302
    query = _redirect_params(response)
    assert "code" in query
    assert "error" not in query

    db.expire_all()
    user = db.scalar(select(User).where(User.email == GITHUB_EMAIL))
    assert user is not None
    assert user.username == GITHUB_LOGIN
    assert user.password_hash is None
    assert user.role_name == "CLIENTE"

    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "github",
            OAuthAccount.provider_account_id == str(GITHUB_ID),
        )
    )
    assert account is not None
    assert account.user_id == user.id

    exchange = client.post("/api/auth/oauth/exchange", json={"code": query["code"][0]})
    assert exchange.status_code == 200, exchange.text
    data = exchange.json()
    assert data["user"]["username"] == GITHUB_LOGIN
    assert data["token_type"] == "bearer"
    cookie = exchange.headers["set-cookie"].lower()
    assert settings.REFRESH_COOKIE_NAME in cookie
    assert "httponly" in cookie

    replay = client.post("/api/auth/oauth/exchange", json={"code": query["code"][0]})
    assert replay.status_code == 401


@respx.mock
def test_callback_reuses_linked_account_without_duplicates(client, db):
    _mock_github()
    first_user = _login_with_github(client, db)

    _mock_github(login="octocat-renamed")
    _, params, _ = _start(client)
    response = _callback(client, params["state"][0])

    assert response.status_code == 302
    assert "code" in _redirect_params(response)
    db.expire_all()
    assert db.scalar(select(User).where(User.email == GITHUB_EMAIL)).id == first_user.id
    assert len(db.scalars(select(OAuthAccount)).all()) == 1
    assert len(db.scalars(select(User)).all()) == 1


@respx.mock
def test_callback_rejects_email_that_belongs_to_local_account(
    client, db, create_user
):
    create_user("trinity")
    _mock_github(email="trinity@test.dev")
    _, params, _ = _start(client)

    response = _callback(client, params["state"][0])

    assert _redirect_params(response)["error"] == ["email_in_use"]
    db.expire_all()
    assert db.scalar(select(OAuthAccount)) is None


@respx.mock
def test_callback_rejects_inactive_linked_user(client, db):
    user = _login_with_github(client, db)
    db.expire_all()
    user = db.get(User, user.id)
    assert user is not None
    user.is_active = False
    db.commit()

    _mock_github()
    _, params, _ = _start(client)
    response = _callback(client, params["state"][0])

    assert _redirect_params(response)["error"] == ["account_disabled"]


@respx.mock
def test_callback_requires_verified_email(client, db):
    _mock_github(emails=[{"email": GITHUB_EMAIL, "primary": True, "verified": False}])
    _, params, _ = _start(client)

    response = _callback(client, params["state"][0])

    assert _redirect_params(response)["error"] == ["email_unverified"]
    db.expire_all()
    assert db.scalar(select(User)) is None


@respx.mock
def test_callback_uses_any_verified_email_when_primary_is_not_verified(client, db):
    _mock_github(
        emails=[
            {"email": "primary@example.com", "primary": True, "verified": False},
            {"email": "secondary@example.com", "primary": False, "verified": True},
        ]
    )
    _, params, _ = _start(client)

    response = _callback(client, params["state"][0])

    assert "code" in _redirect_params(response)
    db.expire_all()
    assert db.scalar(select(User).where(User.email == "secondary@example.com"))


def test_callback_rejects_invalid_state(client):
    _start(client)

    response = _callback(client, "state-manipulado")

    assert _redirect_params(response)["error"] == ["invalid_state"]


def test_callback_rejects_missing_state_cookie(client):
    _, params, _ = _start(client)
    client.cookies.clear()

    response = _callback(client, params["state"][0])

    assert _redirect_params(response)["error"] == ["invalid_state"]


def test_callback_handles_access_denied(client):
    response = client.get(
        "/api/auth/oauth/github/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )

    assert _redirect_params(response)["error"] == ["access_denied"]


def test_callback_requires_code_and_state(client):
    response = client.get(
        "/api/auth/oauth/github/callback",
        follow_redirects=False,
    )

    assert _redirect_params(response)["error"] == ["invalid_request"]


@respx.mock
def test_callback_reports_github_unavailable(client):
    respx.post(oauth_service.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(500)
    )
    _, params, _ = _start(client)

    response = _callback(client, params["state"][0])

    assert _redirect_params(response)["error"] == ["oauth_unavailable"]


def test_exchange_rejects_expired_code(client, db, create_user):
    user = create_user("trinity")
    raw_code = oauth_service.issue_exchange_code(db, user)
    stored = db.scalar(select(OAuthExchangeCode))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = client.post("/api/auth/oauth/exchange", json={"code": raw_code})

    assert response.status_code == 401


def test_exchange_rejects_unknown_code(client):
    response = client.post(
        "/api/auth/oauth/exchange", json={"code": "x" * 43}
    )

    assert response.status_code == 401


@respx.mock
def test_oauth_only_user_cannot_login_with_password(client, db):
    _login_with_github(client, db)

    response = client.post(
        "/api/auth/login",
        json={"username": GITHUB_LOGIN, "password": "Cualquiera123!"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("status", [400, 401, 500])
@respx.mock
def test_callback_reports_github_token_errors(client, status):
    respx.post(oauth_service.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(status, json={"error": "bad_verification_code"})
    )
    _, params, _ = _start(client)

    response = _callback(client, params["state"][0])

    assert _redirect_params(response)["error"] == ["oauth_unavailable"]
