import pytest

from app.core.config import settings
from app.core.rate_limit import LIMITER, Limit, SlidingWindowLimiter

LOGIN_PAYLOAD = {"username": "trinity", "password": "Test1234!"}


@pytest.fixture
def rate_limits_on(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    LIMITER.reset()
    yield
    LIMITER.reset()


def test_login_is_rate_limited_per_identifier(client, create_user, rate_limits_on):
    create_user("trinity")

    for _ in range(5):
        response = client.post("/api/auth/login", json=LOGIN_PAYLOAD)
        assert response.status_code == 200, response.text

    blocked = client.post("/api/auth/login", json=LOGIN_PAYLOAD)

    assert blocked.status_code == 429
    assert "Demasiados intentos" in blocked.json()["detail"]
    assert int(blocked.headers["Retry-After"]) > 0


def test_register_is_rate_limited(client, rate_limits_on):
    for index in range(3):
        response = client.post(
            "/api/auth/register",
            json={
                "username": f"nuevo{index}",
                "email": f"nuevo{index}@test.dev",
                "password": "Secret123!",
            },
        )
        assert response.status_code == 201, response.text

    blocked = client.post(
        "/api/auth/register",
        json={
            "username": "nuevo3",
            "email": "nuevo3@test.dev",
            "password": "Secret123!",
        },
    )

    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]


def test_refresh_is_rate_limited(client, create_user, rate_limits_on):
    create_user("trinity")
    assert client.post("/api/auth/login", json=LOGIN_PAYLOAD).status_code == 200

    for _ in range(30):
        response = client.post("/api/auth/refresh")
        assert response.status_code == 200, response.text

    blocked = client.post("/api/auth/refresh")

    assert blocked.status_code == 429


def test_password_change_is_rate_limited(client, cliente_headers, rate_limits_on):
    payload = {"current_password": "Incorrecta123!", "new_password": "Nueva1234!"}

    for _ in range(5):
        response = client.post(
            "/api/auth/password", json=payload, headers=cliente_headers
        )
        assert response.status_code == 401

    blocked = client.post("/api/auth/password", json=payload, headers=cliente_headers)

    assert blocked.status_code == 429


def test_rate_limit_disabled_does_not_block(client, create_user):
    create_user("trinity")

    for _ in range(8):
        response = client.post("/api/auth/login", json=LOGIN_PAYLOAD)
        assert response.status_code == 200, response.text


def test_sliding_window_limiter_expires_attempts():
    now = 0.0
    limiter = SlidingWindowLimiter(clock=lambda: now)
    limit = Limit(attempts=2, window_seconds=10)

    assert limiter.check("ip", limit) is None
    assert limiter.check("ip", limit) is None
    assert limiter.check("ip", limit) == 11

    now = 10.5
    assert limiter.check("ip", limit) is None
