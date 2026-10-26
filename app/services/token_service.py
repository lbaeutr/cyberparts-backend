from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_refresh_token
from app.models.token import RefreshToken
from app.models.user import User
from app.services.errors import UnauthorizedError


def issue_refresh_token(db: Session, user: User) -> str:
    raw = generate_refresh_token()
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(token)
    db.commit()
    return raw


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[User, str]:
    token_hash = hash_refresh_token(raw_token)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if stored is None or stored.revoked or stored.expires_at < datetime.now(UTC):
        raise UnauthorizedError("Refresh token invalido o expirado")

    stored.revoked = True
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Usuario no valido")

    new_raw = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return user, new_raw


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if stored is not None and not stored.revoked:
        stored.revoked = True
        db.commit()


def revoke_user_tokens(
    db: Session, user_id: int, keep_raw_token: str | None = None
) -> None:
    keep_hash = hash_refresh_token(keep_raw_token) if keep_raw_token else None
    tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked.is_(False),
        )
    ).all()

    changed = False
    for token in tokens:
        if keep_hash is not None and token.token_hash == keep_hash:
            continue
        token.revoked = True
        changed = True
    if changed:
        db.commit()
