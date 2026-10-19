from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Productos"])

staff = require_roles("ADMIN", "GESTOR")


@router.get("", response_model=list[ProductRead])
def list_products(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    only_active: bool = Query(default=True),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Product]:
    return product_service.list_products(
        db,
        category=category,
        search=search,
        only_active=only_active,
        skip=skip,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)) -> Product:
    return product_service.get_product(db, product_id)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: object = Depends(staff),
) -> Product:
    return product_service.create_product(db, payload)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(staff),
) -> Product:
    return product_service.update_product(db, product_id, payload)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(staff),
) -> None:
    product_service.deactivate_product(db, product_id)
