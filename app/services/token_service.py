import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_refresh_token
from app.models.token import RefreshToken
from app.models.user import User
from app.services.errors import UnauthorizedError

logger = logging.getLogger(__name__)

INVALID_REFRESH_DETAIL = "Refresh token invalido o expirado"


def _new_refresh_token(user: User, family_id: str) -> tuple[str, RefreshToken]:
    raw = generate_refresh_token()
    token = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_refresh_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return raw, token


def issue_refresh_token(db: Session, user: User) -> str:
    raw, token = _new_refresh_token(user, uuid.uuid4().hex)
    db.add(token)
    db.commit()
    return raw


def _revoke_family(db: Session, family_id: str, now: datetime) -> int:
    tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked.is_(False),
        )
    ).all()
    for token in tokens:
        token.revoked = True
        token.revoked_at = now
    return len(tokens)


def _handle_reuse(db: Session, stored: RefreshToken, now: datetime) -> None:
    grace = timedelta(seconds=settings.REFRESH_REUSE_GRACE_SECONDS)
    within_grace = (
        stored.revoked_at is not None and now - stored.revoked_at <= grace
    )
    if within_grace:
        logger.info(
            "Reutilizacion de refresh token dentro de la ventana de gracia (family=%s)",
            stored.family_id,
        )
        return

    revoked = _revoke_family(db, stored.family_id, now)
    db.commit()
    logger.warning(
        "Reutilizacion de refresh token detectada; revocada la familia %s (%s tokens)",
        stored.family_id,
        revoked,
    )


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[User, str]:
    token_hash = hash_refresh_token(raw_token)
    stored = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    if stored is None:
        raise UnauthorizedError(INVALID_REFRESH_DETAIL)

    now = datetime.now(UTC)

    if stored.revoked:
        _handle_reuse(db, stored, now)
        raise UnauthorizedError(INVALID_REFRESH_DETAIL)

    if stored.expires_at < now:
        raise UnauthorizedError(INVALID_REFRESH_DETAIL)

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Usuario no valido")

    stored.revoked = True
    stored.revoked_at = now
    new_raw, new_token = _new_refresh_token(user, stored.family_id)
    db.add(new_token)
    db.commit()
    return user, new_raw


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if stored is None:
        return
    now = datetime.now(UTC)
    stored.revoked = True
    stored.revoked_at = now
    _revoke_family(db, stored.family_id, now)
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

    now = datetime.now(UTC)
    changed = False
    for token in tokens:
        if keep_hash is not None and token.token_hash == keep_hash:
            continue
        token.revoked = True
        token.revoked_at = now
        changed = True
    if changed:
        db.commit()
