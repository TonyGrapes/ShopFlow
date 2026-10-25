# app/api/v1/endpoints/products.py
import asyncio
import logging
import random
from decimal import Decimal
from typing import Optional

import magic
from app.api.v1.deps import (
    User,
    get_cache_service,
    get_current_active_user,
    require_deleted_access,
    require_roles,
)
from app.core.config import get_settings
from app.db.enum import ProductStatus, UserRole
from app.db.session import get_db
from app.models.product import Product, ProductImage
from app.schemas.common import Paginated
from app.schemas.product import (
    ProductBulkStatusResponse,
    ProductBulkStatusUpdate,
    ProductCreate,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)
from app.services import product_service
from app.services.cache_keys import (
    build_product_list_cache_key,
    product_list_cache_pattern,
)
from app.services.cache_service import CacheService
from app.services.product_service import (
    serialize_product,
    serialize_product_list_item,
)
from app.services.storage_service import (
    MAX_SIZE,
    MinioStorage,
    get_storage,
    make_object_key,
)
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
require_write_role = require_roles(UserRole.ADMIN, UserRole.MODERATOR, UserRole.SELLER)


# ============================================================
#  Read — публичные + кэш + X-Cache
# ============================================================

@router.get("", response_model=Paginated[ProductListItem])
async def list_products(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None, description="Фильтр по категории"),
    min_cost: Optional[Decimal] = Query(None, ge=0, description="Минимальная цена"),
    max_cost: Optional[Decimal] = Query(None, ge=0, description="Максимальная цена"),
    status_filter: Optional[ProductStatus] = Query(None, alias="status"),
    sort_by: str = Query("id", pattern="^(id|name|cost|created_at)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    include_deleted: bool = Depends(require_deleted_access),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """
    Список товаров: фильтры + сортировка + пагинация + кэш.

    ✅ Cache hit → мгновенный ответ + X-Cache: HIT.
    ✅ Cache miss → запрос в БД + запись в кэш + X-Cache: MISS.
    ✅ Инвалидация при мутациях (POST/PATCH/DELETE) через BackgroundTasks.
    ✅ include_deleted=True → X-Cache: BYPASS (кэш не используется).
    """
    settings = get_settings()

    # ← ИЗМЕНЕНО: при include_deleted полностью обходим кэш.
    #   Смешивать публичный и админский списки в одном ключе нельзя —
    #   ключ не учитывает этот флаг, и админ получил бы закэшированный
    #   публичный результат (без deleted).
    if include_deleted:
        items, total = await product_service.list_products(
            db,
            page=page,
            page_size=page_size,
            category_id=category_id,
            min_cost=min_cost,
            max_cost=max_cost,
            status=status_filter,
            sort_by=sort_by,
            sort_order=sort_order,
            include_deleted=True,
        )
        response.headers["X-Cache"] = "BYPASS"
        return Paginated[ProductListItem](
            items=[serialize_product_list_item(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    cache_key = build_product_list_cache_key(
        page=page,
        page_size=page_size,
        category_id=category_id,
        min_cost=min_cost,
        max_cost=max_cost,
        status=status_filter,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # 1. Проверяем кэш
    cached = await cache.get_json(cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return Paginated[ProductListItem].model_validate(cached)

    # 2. Cache miss — запрос в БД
    items, total = await product_service.list_products(
        db,
        page=page,
        page_size=page_size,
        category_id=category_id,
        min_cost=min_cost,
        max_cost=max_cost,
        status=status_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        include_deleted=False,
    )

    result = Paginated[ProductListItem](
        items=[serialize_product_list_item(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    ttl = (
        settings.PRODUCT_LIST_CACHE_TTL_SECONDS
        + random.randint(0, settings.PRODUCT_LIST_CACHE_TTL_JITTER_SECONDS)
    )
    await cache.set_json(
        cache_key,
        result.model_dump(mode="json"),
        ttl_seconds=ttl,
    )

    response.headers["X-Cache"] = "MISS"
    return result


# ============================================================
#  Bulk — ДО роутов с {product_id}
# ============================================================
#  Порядок: статические сегменты (bulk) должны быть объявлены
#  до динамических ({product_id}), иначе FastAPI попытается
#  распарсить "bulk" как int → 422.
# ============================================================

@router.post(
    "/bulk/status",
    response_model=ProductBulkStatusResponse,
    dependencies=[Depends(require_write_role)],
)
async def bulk_update_status(
    data: ProductBulkStatusUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """
    Bulk update статуса. Один SQL, атомарно.

    Обновляет только активные товары (deleted_at IS NULL).
    Soft-deleted НЕ трогаем — их надо сначала восстановить.

    Инвалидация кэша каталога — через BackgroundTasks после commit.
    """
    result = await db.execute(
        update(Product)
        .where(
            Product.id.in_(data.product_ids),
            Product.deleted_at.is_(None),
        )
        .values(status=data.status)
        .returning(Product.id)
    )
    updated_ids = [row[0] for row in result.all()]
    await db.flush()

    background_tasks.add_task(
        cache.delete_by_pattern,
        product_list_cache_pattern(),
    )

    return ProductBulkStatusResponse(
        updated=len(updated_ids),
        product_ids=updated_ids,
    )


# ============================================================
#  Read: единичный товар — ПОСЛЕ bulk
# ============================================================

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Товар по ID. НЕ кэшируем — редко запрашивается, часто меняется."""
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return serialize_product(product)


# ============================================================
#  Write — с авторизацией + инвалидация кэша
# ============================================================

@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_role)],
)
async def create_product(
    data: ProductCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """Создание. Инвалидация кэша после commit."""
    product = await product_service.create_product(db, data)

    background_tasks.add_task(
        cache.delete_by_pattern,
        product_list_cache_pattern(),
    )

    return serialize_product(product)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(require_write_role)],
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """PATCH. Инвалидация кэша после commit."""
    product = await product_service.update_product(db, product_id, data)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    background_tasks.add_task(
        cache.delete_by_pattern,
        product_list_cache_pattern(),
    )

    return serialize_product(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_write_role)],
)
async def delete_product(
    product_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """Soft delete. Инвалидация кэша после commit."""
    deleted = await product_service.delete_product(db, product_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    background_tasks.add_task(
        cache.delete_by_pattern,
        product_list_cache_pattern(),
    )

    return None


# ============================================================
#  Images — инвалидация тоже нужна
# ============================================================

@router.post(
    "/{product_id}/images",
    response_model=ProductResponse,
    dependencies=[Depends(require_write_role)],
)
async def upload_product_image(
    product_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: MinioStorage = Depends(get_storage),
    cache: CacheService = Depends(get_cache_service),
):
    """Загрузка изображения. Инвалидация кэша после commit (cover_url меняется)."""
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")

    if not file.filename:
        raise HTTPException(400, "File name is required")

    if file.size is not None and file.size > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {file.size} > {MAX_SIZE}",
        )

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"File too large: {len(content)} > {MAX_SIZE}")

    real_mime = await asyncio.to_thread(magic.from_buffer, content, mime=True)
    if real_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(415, f"Unsupported file content: {real_mime}")

    try:
        key = make_object_key(file.filename, product_id=product_id)
    except ValueError as e:
        raise HTTPException(415, str(e))

    try:
        await storage.upload(
            key=key, data=content, size=len(content), content_type=real_mime,
        )
    except Exception:
        logger.exception("MinIO upload failed for key=%s", key)
        raise HTTPException(500, "Failed to upload image")

    try:
        image = ProductImage(product_id=product_id, key=key)
        db.add(image)
        await db.flush()
        await db.refresh(product, ["images"])
    except Exception:
        logger.exception("DB insert failed for key=%s, compensating", key)
        try:
            await storage.delete(key)
        except Exception:
            logger.exception("Compensation failed for key=%s", key)
        raise HTTPException(500, "Failed to save image metadata")

    background_tasks.add_task(
        cache.delete_by_pattern,
        product_list_cache_pattern(),
    )

    return serialize_product(product)


@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_write_role)],
)
async def delete_product_image(
    product_id: int,
    image_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    storage: MinioStorage = Depends(get_storage),
    cache: CacheService = Depends(get_cache_service),
):
    """Удаление. Строка → БД, файл → BackgroundTask, кэш → BackgroundTask."""
    image = await db.get(ProductImage, image_id)
    if image is None or image.product_id != product_id:
        raise HTTPException(404, "Image not found")

    key = image.key
    await db.delete(image)
    await db.flush()

    background_tasks.add_task(_delete_object_safe, storage, key)

    background_tasks.add_task(
        cache.delete_by_pattern,
        product_list_cache_pattern(),
    )

    return None


async def _delete_object_safe(storage: MinioStorage, key: str) -> None:
    """Best-effort удаление файла — ошибки в лог."""
    try:
        await storage.delete(key=key)
    except Exception:
        logger.exception("Failed to delete %s from MinIO (orphan)", key)