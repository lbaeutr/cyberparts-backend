from sqlalchemy import select

from app.models.enums import RoleName
from app.models.role import Role
from app.models.user import User


def test_admin_can_list_users(client, admin_headers, cliente_user):
    response = client.get("/api/users", headers=admin_headers)

    assert response.status_code == 200
    usernames = [u["username"] for u in response.json()]
    assert "admin_test" in usernames
    assert cliente_user.username in usernames


def test_admin_can_paginate_users(client, admin_headers, create_user):
    for index in range(4):
        create_user(f"user_{index}")

    response = client.get("/api/users", params={"limit": 2}, headers=admin_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_admin_can_get_user(client, admin_headers, cliente_user):
    response = client.get(f"/api/users/{cliente_user.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["username"] == cliente_user.username


def test_get_missing_user_returns_404(client, admin_headers):
    response = client.get("/api/users/9999", headers=admin_headers)

    assert response.status_code == 404


def test_non_admin_cannot_list_users(client, gestor_headers, cliente_headers):
    assert client.get("/api/users", headers=gestor_headers).status_code == 403
    assert client.get("/api/users", headers=cliente_headers).status_code == 403


def test_anonymous_cannot_list_users(client):
    response = client.get("/api/users")

    assert response.status_code == 401


def test_admin_can_change_role(client, admin_headers, cliente_user, db):
    response = client.patch(
        f"/api/users/{cliente_user.id}/role",
        json={"role": "GESTOR"},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "GESTOR"
    db.refresh(cliente_user)
    assert cliente_user.role_name == "GESTOR"


def test_admin_cannot_demote_self(client, admin_headers, admin_user):
    response = client.patch(
        f"/api/users/{admin_user.id}/role",
        json={"role": "CLIENTE"},
        headers=admin_headers,
    )

    assert response.status_code == 400


def test_invalid_role_returns_422(client, admin_headers, cliente_user):
    response = client.patch(
        f"/api/users/{cliente_user.id}/role",
        json={"role": "SUPERADMIN"},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_admin_can_deactivate_and_activate_user(client, admin_headers, cliente_user, db):
    deactivated = client.patch(
        f"/api/users/{cliente_user.id}/active",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    db.refresh(cliente_user)
    login = client.post(
        "/api/auth/login",
        json={"username": cliente_user.username, "password": "Test1234!"},
    )
    assert login.status_code == 403

    activated = client.patch(
        f"/api/users/{cliente_user.id}/active",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True


def test_admin_cannot_deactivate_self(client, admin_headers, admin_user):
    response = client.patch(
        f"/api/users/{admin_user.id}/active",
        json={"is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 400


def test_admin_can_delete_other_user_logically(client, admin_headers, cliente_user, db):
    response = client.delete(f"/api/users/{cliente_user.id}", headers=admin_headers)

    assert response.status_code == 204
    db.refresh(cliente_user)
    assert cliente_user.is_active is False
    stored = db.scalar(select(User).where(User.id == cliente_user.id))
    assert stored is not None


def test_admin_cannot_delete_self(client, admin_headers, admin_user):
    response = client.delete(f"/api/users/{admin_user.id}", headers=admin_headers)

    assert response.status_code == 400


def test_gestor_cannot_change_roles(client, gestor_headers, cliente_user):
    response = client.patch(
        f"/api/users/{cliente_user.id}/role",
        json={"role": "GESTOR"},
        headers=gestor_headers,
    )

    assert response.status_code == 403


def test_roles_are_seeded_in_test_database(db):
    roles = set(db.scalars(select(Role.name)).all())

    assert roles == {RoleName.ADMIN, RoleName.GESTOR, RoleName.CLIENTE}
