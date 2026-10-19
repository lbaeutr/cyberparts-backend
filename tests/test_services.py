import pytest

from app.models.enums import OrderStatus
from app.schemas.order import OrderCreate
from app.services import order_service, product_service
from app.services.errors import ConflictError, NotFoundError


def test_product_service_raises_not_found(db):
    with pytest.raises(NotFoundError):
        product_service.get_product(db, 9999)


def test_order_service_rejects_insufficient_stock(db, cliente_user, create_product):
    product = create_product(stock=1)
    payload = OrderCreate(items=[{"product_id": product.id, "quantity": 2}])

    with pytest.raises(ConflictError):
        order_service.create_order(db, cliente_user, payload)


def test_order_service_enforces_status_transitions(db, cliente_user, create_product):
    product = create_product(stock=5)
    payload = OrderCreate(items=[{"product_id": product.id, "quantity": 1}])
    order = order_service.create_order(db, cliente_user, payload)

    paid = order_service.update_status(db, order.id, OrderStatus.PAID)

    assert paid.status == OrderStatus.PAID
    with pytest.raises(ConflictError):
        order_service.update_status(db, order.id, OrderStatus.PENDING)
