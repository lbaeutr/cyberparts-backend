from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import OrderStatus, RoleName
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.user import User
from app.schemas.order import OrderCreate
from app.services.errors import ConflictError, ForbiddenError, NotFoundError

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def create_order(db: Session, user: User, payload: OrderCreate) -> Order:
    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    products: dict[int, Product] = {}
    for product_id in sorted(quantities):
        product = db.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None or not product.is_active:
            raise NotFoundError(f"Producto {product_id} no disponible")

        quantity = quantities[product_id]
        if product.stock < quantity:
            raise ConflictError(
                f"Stock insuficiente para '{product.name}' (disponible: {product.stock})"
            )
        products[product_id] = product

    order = Order(user_id=user.id, status=OrderStatus.PENDING, total=Decimal(0))
    total = Decimal(0)

    for product_id, quantity in quantities.items():
        product = products[product_id]
        product.stock -= quantity
        total += product.price * quantity
        order.items.append(
            OrderItem(
                product_id=product.id,
                quantity=quantity,
                unit_price=product.price,
            )
        )

    order.total = total
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_orders(db: Session, user: User) -> list[Order]:
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.id.desc())
    )
    if user.role_name == RoleName.CLIENTE.value:
        stmt = stmt.where(Order.user_id == user.id)
    return list(db.scalars(stmt).all())


def get_order(db: Session, user: User, order_id: int) -> Order:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    if order is None:
        raise NotFoundError("Pedido no encontrado")
    if user.role_name == RoleName.CLIENTE.value and order.user_id != user.id:
        raise ForbiddenError("Pedido de otro usuario")
    return order


def update_status(db: Session, order_id: int, new_status: OrderStatus) -> Order:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
        .with_for_update()
    )
    if order is None:
        raise NotFoundError("Pedido no encontrado")

    if new_status == order.status:
        return order

    if new_status not in ALLOWED_TRANSITIONS[order.status]:
        raise ConflictError(
            f"Transicion no permitida: {order.status.value} -> {new_status.value}"
        )

    if new_status == OrderStatus.CANCELLED:
        for item in order.items:
            product = db.get(Product, item.product_id, with_for_update=True)
            if product is not None:
                product.stock += item.quantity

    order.status = new_status
    db.commit()
    db.refresh(order)
    return order
