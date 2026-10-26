from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import respx
from sqlalchemy import select

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_refresh_token,
    verify_password,
)
from app.models.enums import RoleName
from app.models.oauth import OAuthAccount
from app.models.role import Role
from app.models.token import RefreshToken
from app.models.user import User
from app.services import oauth_service
from app.services.token_service import issue_refresh_token

GITHUB_ID = 654321
GITHUB_LOGIN = "octocat-link"
GITHUB_EMAIL = "octocat-link@example.com"
DEFAULT_PASSWORD = "Test1234!"
NEW_PASSWORD = "Nueva123!"


def _mock_github(
    account_id: int = GITHUB_ID,
    login: str = GITHUB_LOGIN,
    email: str = GITHUB_EMAIL,
) -> None:
    respx.post(oauth_service.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "github-access-token"})
    )
    respx.get(oauth_service.GITHUB_USER_URL).mock(
        return_value=httpx.Response(200, json={"id": account_id, "login": login})
    )
    respx.get(oauth_service.GITHUB_EMAILS_URL).mock(
        return_value=httpx.Response(
            200, json=[{"email": email, "primary": True, "verified": True}]
        )
    )


def _start_link(client, headers) -> tuple[dict[str, list[str]], str]:
    response = client.get("/api/auth/oauth/github/link/start", headers=headers)
    assert response.status_code == 200, response.text
    params = parse_qs(urlparse(response.json()["authorize_url"]).query)
    state_cookie = client.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)
    assert state_cookie
    return params, state_cookie


def _link(client, headers, code: str = "github-code"):
    params, _ = _start_link(client, headers)
    return client.get(
        "/api/auth/oauth/github/callback",
        params={"state": params["state"][0], "code": code},
        follow_redirects=False,
    )


def _redirect_query(response) -> dict[str, list[str]]:
    return parse_qs(urlparse(response.headers["location"]).query)


def test_me_reports_has_password(client, cliente_user, cliente_headers):
    response = client.get("/api/auth/me", headers=cliente_headers)

    assert response.status_code == 200
    assert response.json()["has_password"] is True


def test_change_password_requires_current_password(client, cliente_user, cliente_headers):
    response = client.post(
        "/api/auth/password",
        json={"new_password": NEW_PASSWORD},
        headers=cliente_headers,
    )

    assert response.status_code == 401


def test_change_password_rejects_wrong_current_password(
    client, cliente_user, cliente_headers
):
    response = client.post(
        "/api/auth/password",
        json={"current_password": "Incorrecta123!", "new_password": NEW_PASSWORD},
        headers=cliente_headers,
    )

    assert response.status_code == 401


def test_change_password_updates_hash_and_revokes_other_sessions(
    client, db, cliente_user, cliente_headers
):
    extra_token = issue_refresh_token(db, cliente_user)
    current_token = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert current_token

    response = client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=cliente_headers,
    )

    assert response.status_code == 204, response.text
    db.expire_all()
    user = db.get(User, cliente_user.id)
    assert user is not None
    assert user.password_hash is not None
    assert verify_password(NEW_PASSWORD, user.password_hash)

    tokens = {
        token.token_hash: token
        for token in db.scalars(
            select(RefreshToken).where(RefreshToken.user_id == cliente_user.id)
        ).all()
    }
    assert tokens[hash_refresh_token(current_token)].revoked is False
    assert tokens[hash_refresh_token(extra_token)].revoked is True

    old_login = client.post(
        "/api/auth/login",
        json={"username": cliente_user.username, "password": DEFAULT_PASSWORD},
    )
    new_login = client.post(
        "/api/auth/login",
        json={"username": cliente_user.username, "password": NEW_PASSWORD},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_oauth_only_user_can_set_password_without_current(
    client, db, create_user
):
    role = db.scalar(select(Role).where(Role.name == RoleName.CLIENTE))
    assert role is not None
    user = User(
        username="github-only",
        email="github-only@test.dev",
        password_hash=None,
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    headers = {
        "Authorization": f"Bearer {create_access_token(str(user.id), user.role_name)}"
    }
    response = client.post(
        "/api/auth/password",
        json={"new_password": NEW_PASSWORD},
        headers=headers,
    )

    assert response.status_code == 204, response.text
    login = client.post(
        "/api/auth/login",
        json={"username": "github-only", "password": NEW_PASSWORD},
    )
    assert login.status_code == 200


def test_oauth_accounts_returns_linked_account(client, db, cliente_user, cliente_headers):
    db.add(
        OAuthAccount(
            user_id=cliente_user.id,
            provider="github",
            provider_account_id="42",
            username="octocat",
            email="octocat@example.com",
        )
    )
    db.commit()

    response = client.get("/api/auth/oauth/accounts", headers=cliente_headers)

    assert response.status_code == 200
    assert response.json()["github"]["username"] == "octocat"


def test_oauth_accounts_returns_null_when_not_linked(client, cliente_headers):
    response = client.get("/api/auth/oauth/accounts", headers=cliente_headers)

    assert response.status_code == 200
    assert response.json()["github"] is None


def test_unlink_github_removes_account(client, db, cliente_user, cliente_headers):
    db.add(
        OAuthAccount(
            user_id=cliente_user.id,
            provider="github",
            provider_account_id="42",
            username="octocat",
            email="octocat@example.com",
        )
    )
    db.commit()

    response = client.delete("/api/auth/oauth/github", headers=cliente_headers)

    assert response.status_code == 204
    db.expire_all()
    assert (
        db.scalar(select(OAuthAccount).where(OAuthAccount.user_id == cliente_user.id))
        is None
    )


def test_unlink_requires_a_password(client, db, create_user):
    role = db.scalar(select(Role).where(Role.name == RoleName.CLIENTE))
    assert role is not None
    user = User(
        username="github-only",
        email="github-only@test.dev",
        password_hash=None,
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(
        OAuthAccount(
            user_id=user.id,
            provider="github",
            provider_account_id="42",
            username="octocat",
            email="octocat@example.com",
        )
    )
    db.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token(str(user.id), user.role_name)}"
    }

    response = client.delete("/api/auth/oauth/github", headers=headers)

    assert response.status_code == 409
    db.expire_all()
    assert db.scalar(select(OAuthAccount).where(OAuthAccount.user_id == user.id))


def test_link_start_requires_authentication(client):
    response = client.get("/api/auth/oauth/github/link/start")

    assert response.status_code == 401


def test_link_start_returns_authorize_url_with_link_state(
    client, cliente_user, cliente_headers
):
    params, state_cookie = _start_link(client, cliente_headers)

    assert params["client_id"] == [settings.GITHUB_CLIENT_ID]
    assert params["code_challenge_method"] == ["S256"]
    payload = jwt.decode(
        state_cookie, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    assert payload["mode"] == "link"
    assert payload["uid"] == cliente_user.id


@respx.mock
def test_link_callback_attaches_github_account(
    client, db, cliente_user, cliente_headers
):
    _mock_github()

    response = _link(client, cliente_headers)

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{settings.frontend_base_url}/perfil")
    assert _redirect_query(response)["oauth"] == ["linked"]

    db.expire_all()
    account = db.scalar(
        select(OAuthAccount).where(OAuthAccount.user_id == cliente_user.id)
    )
    assert account is not None
    assert account.provider_account_id == str(GITHUB_ID)


@respx.mock
def test_link_callback_rejects_github_account_of_another_user(
    client, db, create_user, cliente_headers
):
    other = create_user("other-user")
    db.add(
        OAuthAccount(
            user_id=other.id,
            provider="github",
            provider_account_id=str(GITHUB_ID),
            username=GITHUB_LOGIN,
            email=GITHUB_EMAIL,
        )
    )
    db.commit()
    _mock_github()

    response = _link(client, cliente_headers)

    assert response.status_code == 302
    assert _redirect_query(response)["oauth_error"] == ["github_in_use"]


@respx.mock
def test_link_callback_rejects_second_github_account(
    client, db, cliente_user, cliente_headers
):
    db.add(
        OAuthAccount(
            user_id=cliente_user.id,
            provider="github",
            provider_account_id="111",
            username="previo",
            email="previo@example.com",
        )
    )
    db.commit()
    _mock_github()

    response = _link(client, cliente_headers)

    assert response.status_code == 302
    assert _redirect_query(response)["oauth_error"] == ["github_already_linked"]


def test_link_callback_access_denied_redirects_to_profile(client, cliente_headers):
    params, _ = _start_link(client, cliente_headers)

    response = client.get(
        "/api/auth/oauth/github/callback",
        params={"state": params["state"][0], "error": "access_denied"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{settings.frontend_base_url}/perfil")
    assert _redirect_query(response)["oauth_error"] == ["access_denied"]
