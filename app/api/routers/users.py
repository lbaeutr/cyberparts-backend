from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserActiveUpdate, UserRead, UserRoleUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Usuarios"])

admin_only = require_roles("ADMIN")


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: object = Depends(admin_only),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[User]:
    return user_service.list_users(db, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(admin_only),
) -> User:
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}/role", response_model=UserRead)
def update_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(admin_only),
) -> User:
    return user_service.update_role(db, current, user_id, payload.role)


@router.patch("/{user_id}/active", response_model=UserRead)
def update_active(
    user_id: int,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(admin_only),
) -> User:
    return user_service.update_active(db, current, user_id, payload.is_active)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(admin_only),
) -> None:
    user_service.deactivate_user(db, current, user_id)
