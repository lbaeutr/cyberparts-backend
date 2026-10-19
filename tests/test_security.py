from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_hash_password_uses_random_salt():
    first = hash_password("Secreto123!")
    second = hash_password("Secreto123!")

    assert first != second
    assert first.startswith("$2b$")
    assert verify_password("Secreto123!", first)
    assert not verify_password("otra-clave", first)


def test_hash_password_truncates_to_bcrypt_limit():
    base = "a" * 72
    hashed = hash_password(base + "primera")
    second = hash_password(base + "segunda")

    assert verify_password(base + "primera", hashed)
    assert verify_password(base + "segunda", second)
    assert verify_password(base + "primera", second)


def test_verify_password_with_invalid_hash():
    assert not verify_password("clave", "no-es-un-hash")


def test_access_token_roundtrip():
    token = create_access_token("42", "ADMIN")

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"


def test_expired_access_token_raises():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "role": "CLIENTE",
            "type": "access",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_refresh_tokens_are_opaque_and_hashed():
    raw = generate_refresh_token()
    other = generate_refresh_token()

    assert raw != other
    assert len(raw) >= 64
    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != raw
