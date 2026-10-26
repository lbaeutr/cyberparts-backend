import os
from decimal import Decimal

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://cyberparts:cyberparts@127.0.0.1:5432/cyberparts_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ["COOKIE_SECURE"] = "false"
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("FRONTEND_URL", "http://frontend.test")
os.environ.setdefault(
    "GITHUB_REDIRECT_URI", "http://api.test/api/auth/oauth/github/callback"
)

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Role, User
from app.models.enums import RoleName
from app.models.product import Product

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_PASSWORD = "Test1234!"
ROLE_DESCRIPTIONS = {
    RoleName.ADMIN: "Administrador",
    RoleName.GESTOR: "Gestor",
    RoleName.CLIENTE: "Cliente",
}


def _ensure_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    dbname = url.database
    admin_dsn = os.environ.get("TEST_ADMIN_DSN", "postgresql:///postgres?host=/tmp")

    try:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
            ).fetchone()
            if not exists:
                owner = url.username or "postgres"
                conn.execute(f'CREATE DATABASE "{dbname}" OWNER "{owner}"')
    except psycopg.Error as exc:
        raise RuntimeError(
            "No se pudo preparar la base de datos de test. Ejecuta ./scripts/test.sh"
        ) from exc

    try:
        with psycopg.connect(
            host=url.host or "/tmp",
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            dbname=dbname,
        ):
            pass
    except psycopg.Error as exc:
        raise RuntimeError(
            f"No se pudo conectar a la base de datos de test '{dbname}'. "
            "Ejecuta ./scripts/test.sh"
        ) from exc


_ensure_test_database()


@pytest.fixture(scope="session", autouse=True)
def _fast_bcrypt():
    import bcrypt

    original = bcrypt.gensalt

    def gensalt(rounds=4, prefix=b"2b"):
        return original(rounds=rounds, prefix=prefix)

    bcrypt.gensalt = gensalt
    yield
    bcrypt.gensalt = original


@pytest.fixture(scope="session", autouse=True)
def _schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _reset_db():
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE oauth_exchange_codes, oauth_accounts, order_items, "
                "orders, refresh_tokens, products, users, roles "
                "RESTART IDENTITY CASCADE"
            )
        )
    with SessionLocal() as db:
        db.add_all(
            [Role(name=name, description=description) for name, description in ROLE_DESCRIPTIONS.items()]
        )
        db.commit()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def create_user(db):
    def _create(
        username: str,
        role: RoleName = RoleName.CLIENTE,
        password: str = DEFAULT_PASSWORD,
        is_active: bool = True,
    ) -> User:
        role_obj = db.scalar(select(Role).where(Role.name == role))
        assert role_obj is not None
        user = User(
            username=username,
            email=f"{username}@test.dev",
            password_hash=hash_password(password),
            role_id=role_obj.id,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _create


@pytest.fixture
def create_product(db):
    def _create(**overrides) -> Product:
        data = {
            "name": "Servomotor X1",
            "description": "Servo de alta precision",
            "category": "Servomotores",
            "price": Decimal("99.99"),
            "stock": 10,
            "is_active": True,
        }
        data.update(overrides)
        product = Product(**data)
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    return _create


@pytest.fixture
def login(client):
    def _login(username: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def admin_user(create_user):
    return create_user("admin_test", RoleName.ADMIN)


@pytest.fixture
def gestor_user(create_user):
    return create_user("gestor_test", RoleName.GESTOR)


@pytest.fixture
def cliente_user(create_user):
    return create_user("cliente_test", RoleName.CLIENTE)


@pytest.fixture
def admin_headers(admin_user, login):
    return login(admin_user.username)


@pytest.fixture
def gestor_headers(gestor_user, login):
    return login(gestor_user.username)


@pytest.fixture
def cliente_headers(cliente_user, login):
    return login(cliente_user.username)
