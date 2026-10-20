from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.user import User
from app.schemas.order import OrderCreate, OrderRead, OrderStatusUpdate
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Pedidos"])

staff = require_roles("ADMIN", "GESTOR")


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Order:
    return order_service.create_order(db, current_user, payload)


@router.get("", response_model=list[OrderRead])
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Order]:
    return order_service.list_orders(
        db, current_user, status_filter=status_filter, skip=skip, limit=limit
    )


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Order:
    return order_service.get_order(db, current_user, order_id)


@router.patch("/{order_id}/status", response_model=OrderRead)
def update_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(staff),
) -> Order:
    return order_service.update_status(db, order_id, payload.status)
