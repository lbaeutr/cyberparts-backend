from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RoleName
from app.models.role import Role
from app.models.user import User
from app.services.errors import BadRequestError, NotFoundError


def list_users(db: Session, *, skip: int = 0, limit: int = 100) -> list[User]:
    stmt = select(User).order_by(User.id).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Usuario no encontrado")
    return user


def update_role(db: Session, actor: User, user_id: int, role_name: RoleName) -> User:
    user = get_user(db, user_id)

    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise BadRequestError("Rol inexistente")

    if user.id == actor.id and role.name != RoleName.ADMIN:
        raise BadRequestError("No puedes quitarte a ti mismo el rol ADMIN")

    user.role_id = role.id
    db.commit()
    db.refresh(user)
    return user


def update_active(db: Session, actor: User, user_id: int, is_active: bool) -> User:
    user = get_user(db, user_id)
    if user.id == actor.id and not is_active:
        raise BadRequestError("No puedes desactivar tu propia cuenta")

    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, actor: User, user_id: int) -> None:
    user = get_user(db, user_id)
    if user.id == actor.id:
        raise BadRequestError("No puedes eliminar tu propia cuenta")

    user.is_active = False
    db.commit()
