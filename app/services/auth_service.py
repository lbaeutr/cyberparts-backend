from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.enums import RoleName
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserRegister
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    InternalError,
    UnauthorizedError,
)
from app.services.token_service import issue_refresh_token


def register_user(db: Session, payload: UserRegister) -> User:
    existing = db.scalar(
        select(User).where(
            or_(
                User.username == payload.username,
                func.lower(User.email) == payload.email.lower(),
            )
        )
    )
    if existing is not None:
        raise ConflictError("El usuario o correo ya esta registrado")

    cliente_role = db.scalar(select(Role).where(Role.name == RoleName.CLIENTE))
    if cliente_role is None:
        raise InternalError("Rol CLIENTE no inicializado")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role_id=cliente_role.id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("El usuario o correo ya esta registrado") from exc
    db.refresh(user)
    return user


def login_user(db: Session, username: str, password: str) -> tuple[User, str]:
    user = db.scalar(
        select(User).where(
            or_(
                User.username == username,
                func.lower(User.email) == username.lower(),
            )
        )
    )
    if user is None or user.password_hash is None:
        raise UnauthorizedError("Credenciales incorrectas")
    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("Credenciales incorrectas")
    if not user.is_active:
        raise ForbiddenError("Usuario desactivado")

    return user, issue_refresh_token(db, user)
