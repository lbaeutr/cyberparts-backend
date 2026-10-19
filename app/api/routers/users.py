from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.enums import RoleName
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserActiveUpdate, UserRead, UserRoleUpdate

router = APIRouter(prefix="/users", tags=["Usuarios"])

admin_only = require_roles("ADMIN")


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: object = Depends(admin_only),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[User]:
    stmt = select(User).order_by(User.id).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(admin_only),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user


@router.patch("/{user_id}/role", response_model=UserRead)
def update_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(admin_only),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    role = db.scalar(select(Role).where(Role.name == RoleName(payload.role)))
    if role is None:
        raise HTTPException(status_code=400, detail="Rol inexistente")

    if user.id == current.id and role.name != RoleName.ADMIN:
        raise HTTPException(status_code=400, detail="No puedes quitarte a ti mismo el rol ADMIN")

    user.role_id = role.id
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/active", response_model=UserRead)
def update_active(
    user_id: int,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(admin_only),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user.id == current.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(admin_only),
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")
    user.is_active = False
    db.commit()
