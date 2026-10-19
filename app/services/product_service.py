from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.errors import NotFoundError


def list_products(
    db: Session,
    *,
    category: str | None = None,
    search: str | None = None,
    only_active: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[Product]:
    stmt = select(Product)
    if only_active:
        stmt = stmt.where(Product.is_active.is_(True))
    if category:
        stmt = stmt.where(Product.category == category)
    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Product.id).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Producto no encontrado")
    return product


def create_product(db: Session, payload: ProductCreate) -> Product:
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product_id: int, payload: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def deactivate_product(db: Session, product_id: int) -> None:
    product = get_product(db, product_id)
    product.is_active = False
    db.commit()
