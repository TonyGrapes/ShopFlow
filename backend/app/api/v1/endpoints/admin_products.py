"""
Админские эндпоинты товаров.

RBAC (per-endpoint):
- list / create / patch — ADMIN | MODERATOR
- hard-delete — только ADMIN (необратимо)

Отличия от публичного /products:
- список включает soft-deleted (deleted_at не фильтруется);
- можно hard-удалить (только если товар не в заказах);
- кэш не используется — админ видит актуальное состояние.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.core.exceptions import ConflictError
from app.db.enum import ProductSortBy, ProductStatus, SortOrder, UserRole
from app.db.session import get_db
from app.models.order_item import OrderItem
from app.models.product import Product
from app.schemas.common import Paginated
from app.schemas.product import (
    ProductCreate,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)
from app.services import product_service
from app.services.product_service import (
    serialize_product,
    serialize_product_list_item,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/products", tags=["admin:products"])


@router.get(
    "",
    response_model=Paginated[ProductListItem],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def list_admin_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, min_length=1, max_length=100),
    category_id: int | None = Query(None),
    status_filter: ProductStatus | None = Query(None, alias="status"),
    sort_by: ProductSortBy = Query(ProductSortBy.ID),
    sort_order: SortOrder = Query(SortOrder.ASC),
    db: AsyncSession = Depends(get_db),
):
    """Список ВСЕХ товаров, включая soft-deleted. Без кэша."""
    items, total = await product_service.list_products(
        db,
        page=page,
        page_size=page_size,
        category_id=category_id,
        q=q,
        status=status_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        include_deleted=True,          # ← ключевое отличие
    )
    return Paginated[ProductListItem](
        items=[serialize_product_list_item(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def create_admin_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
):
    """Создание. Переиспользует product_service (валидация + 409 на дубль имени)."""
    product = await product_service.create_product(db, data)
    return serialize_product(product)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def update_admin_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    """PATCH. Переиспользует product_service."""
    product = await product_service.update_product(db, product_id, data)
    if product is None:
        raise HTTPException(404, "Product not found")
    return serialize_product(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],   # только ADMIN
)
async def delete_admin_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Hard-delete. Только ADMIN.

    409, если товар используется в заказах — сохраняем историю.
    В этом случае ADMIN должен сделать soft-delete через публичный
    DELETE /products/{id} (он делает soft).
    """
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")

    in_orders = (await db.execute(
        select(OrderItem.id).where(OrderItem.product_id == product_id).limit(1)
    )).scalar_one_or_none()
    if in_orders is not None:
        raise ConflictError(
            "Product is used in orders; use soft-delete instead",
            code="product_has_orders",
        )

    await db.delete(product)
    await db.flush()
    return None