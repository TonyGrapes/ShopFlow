# app/services/product_service.py
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ValidationError
from app.db.enum import ProductStatus
from app.db.errors import is_unique_violation
from app.models.category import Category
from app.models.product import Product
from app.schemas.product import (
    CategoryBrief,
    ProductCreate,
    ProductImageBrief,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)

# ✅ Имя партиального индекса уникальности активного имени товара
_ACTIVE_NAME_CONSTRAINT = "idx_product_active_name"


async def list_products(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    category_id: int | None = None,
    min_cost: Decimal | None = None,
    max_cost: Decimal | None = None,
    status: ProductStatus | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
    include_deleted: bool = False,      # ← НОВОЕ
) -> tuple[list[Product], int]:
    base_query = select(Product)
    if not include_deleted:
        base_query = base_query.where(Product.deleted_at.is_(None))

    if category_id is not None:
        base_query = base_query.where(Product.category_id == category_id)
    if min_cost is not None:
        base_query = base_query.where(Product.cost >= min_cost)
    if max_cost is not None:
        base_query = base_query.where(Product.cost <= max_cost)
    if status is not None:
        base_query = base_query.where(Product.status == status)

    # COUNT
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Сортировка
    sort_column = {
        "id": Product.id,
        "name": Product.name,
        "cost": Product.cost,
        "created_at": Product.created_at,
    }.get(sort_by, Product.id)
    order_func = desc if sort_order == "desc" else asc

    # Items
    items_query = (
        base_query
        .options(selectinload(Product.category), selectinload(Product.images))
        .order_by(order_func(sort_column), Product.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(items_query)).scalars().all()
    return items, total

# ---------- Сериализация ----------

def serialize_product(product: Product) -> ProductResponse:
    """Возвращает Pydantic-схему с публичными URL."""
    storage = get_storage()
    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        cost=product.cost,
        category_id=product.category_id,
        status=product.status,
        category=CategoryBrief.model_validate(product.category) if product.category else None,
        images=[
            ProductImageBrief(id=img.id, url=storage.get_url(img.key))
            for img in product.images
        ],
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def serialize_product_list_item(product: Product) -> ProductListItem:
    storage = get_storage()
    return ProductListItem(
        id=product.id,
        name=product.name,
        cost=product.cost,
        status=product.status,
        cover_url=storage.get_url(product.cover_key) if product.cover_key else None,
    )

# ---------- CRUD ----------

async def get_product(db: AsyncSession, product_id: int) -> Product | None:
    """Товар по ID. Фильтр удалённых + selectinload связей."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id, Product.deleted_at.is_(None))
        .options(selectinload(Product.category), selectinload(Product.images))
    )
    return result.scalar_one_or_none()


async def create_product(db: AsyncSession, data: ProductCreate) -> Product:
    """
    Создание.

    ✅ Нарушение уникальности активного имени → 409 Conflict.
    ✅ flush вместо commit — фиксация в get_db.
    """
    if data.category_id is not None:
        category = await db.get(Category, data.category_id)
        if category is None:
            raise ValidationError(
                f"Category {data.category_id} not found",
                code="invalid_category",
                extra={"category_id": data.category_id},
            )

    product = Product(**data.model_dump())
    db.add(product)

    try:
        await db.flush()                # ← здесь может вылететь IntegrityError
    except IntegrityError as exc:

        if is_unique_violation(exc, _ACTIVE_NAME_CONSTRAINT):
            raise ConflictError(
                f"Product with name '{data.name}' already exists",
                code="name_taken"
                ) from exc

        # Не unique-violation или другой constraint — не наша ответственность
        logger.exception("Unexpected IntegrityError on create_product")
        raise

    return await get_product(db, product.id)


async def update_product(
    db: AsyncSession, product_id: int, data: ProductUpdate
) -> Product | None:
    """
    PATCH.

    ✅ Переименование в занятое имя → 409.
    ✅ flush вместо commit.
    """
    product = await get_product(db, product_id)
    if product is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if "category_id" in update_data and update_data["category_id"] is not None:
        category = await db.get(Category, update_data["category_id"])
        if category is None:
            raise ValidationError(
                f"Category {update_data['category_id']} not found",
                code="invalid_category",
                extra={"category_id": update_data["category_id"]},
            )
        
    for field, value in update_data.items():
        setattr(product, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        if is_unique_violation(exc, _ACTIVE_NAME_CONSTRAINT):
            new_name = update_data.get("name") or "existing"
            raise ConflictError(
                f"Product with name '{new_name}' already exists",
                code="name_taken",
                ) from exc
        logger.exception("Unexpected IntegrityError on update_product")
        raise

    return await get_product(db, product.id)


async def delete_product(db: AsyncSession, product_id: int) -> bool:
    """
    Soft delete. Файлы НЕ удаляются.

    Товар жив в истории заказов (order_items). Физическая очистка
    файлов — задача hard delete / фоновой задачи.
    """
    product = await get_product(db, product_id)
    if product is None:
        return False

    product.deleted_at = datetime.now(UTC)
    await db.flush()
    return True