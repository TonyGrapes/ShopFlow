"""
Сервис отзывов.

Контракт:
- Отзыв можно оставить только на товар, который был получен
  (Order.status == DELIVERED и товар есть в OrderItem).
- Один активный отзыв на (user, product). Partial unique index.
- Удаление — soft-delete. Аудит сохраняется.
- is_verified=True всегда (т.к. пишем только после delivered).
- Список и summary — публичны.

Reason'ы ошибок при POST:
- 404 product_not_found  — товар не существует / soft-deleted.
- 403 no_delivered_order — нет delivered-заказа с этим товаром.
- 409 already_reviewed   — активный отзыв уже есть.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError
from app.db.enum import OrderStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.schemas.review import (
    ReviewCreate,
    ReviewResponse,
    ReviewSummaryResponse,
    ReviewUserBrief,
)

logger = logging.getLogger(__name__)

_ACTIVE_REVIEW_CONSTRAINT = "uq_review_user_product"


# ============================================================
#  Поиск delivered-заказа
# ============================================================

async def get_reviewable_order(
    db: AsyncSession, user_id: int, product_id: int
) -> Optional[Order]:
    """
    Возвращает последний delivered-заказ юзера, содержащий товар.

    None — если юзер не получал этот товар.
    «Последний» — по created_at DESC, id DESC (tie-breaker).
    """
    result = await db.execute(
        select(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == user_id,
            Order.status == OrderStatus.DELIVERED,
            OrderItem.product_id == product_id,
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ============================================================
#  Создание отзыва
# ============================================================

async def create_review(
    db: AsyncSession, user: User, data: ReviewCreate
) -> Review:
    """
    Создаёт отзыв.

    Проверки:
    1. Товар существует и не удалён → 404.
    2. Есть delivered-заказ юзера с этим товаром → 403.
    3. Нет активного отзыва на этот товар → 409.
    """
    # 1. Товар
    product = await db.get(Product, data.product_id)
    if product is None or product.deleted_at is not None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "product_not_found",
                "product_id": data.product_id,
            },
        )

    # 2. Delivered-заказ
    order = await get_reviewable_order(db, user.id, data.product_id)
    if order is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "no_delivered_order",
                "message": "You can only review products you have received",
            },
        )

    # 3. Активный отзыв уже есть
    existing = (await db.execute(
        select(Review).where(
            Review.user_id == user.id,
            Review.product_id == data.product_id,
            Review.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("You already reviewed this product", code="already_reviewed")

    # 4. Создание
    review = Review(
        user_id=user.id,
        product_id=data.product_id,
        order_id=order.id,
        rating=data.rating,
        title=data.title,
        comment=data.comment,
        is_verified=True,   # ✅ Всегда True: пишем только после delivered
    )
    db.add(review)

    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_active_review_conflict(exc):
            raise ConflictError("already reviewed", code="already_reviewed") from exc
        logger.exception("Unexpected IntegrityError on create_review")
        raise

    # Перезагружаем с user для сериализации
    return await _load_review(db, review.id)


# ============================================================
#  Чтение отзывов товара
# ============================================================

_SORT_COLUMNS = {
    "created_at": Review.created_at,
    "rating": Review.rating,
}


async def list_product_reviews(
    db: AsyncSession,
    product_id: int,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Review], int]:
    """
    Список активных отзывов товара.

    sort_by из белого списка (_SORT_COLUMNS). Иначе — дефолт created_at.
    Tie-breaker: id DESC — детерминированный порядок.
    """
    sort_column = _SORT_COLUMNS.get(sort_by, Review.created_at)
    order_func = desc if sort_order == "desc" else asc

    base_query = select(Review).where(
        Review.product_id == product_id,
        Review.deleted_at.is_(None),
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    items_query = (
        base_query
        .options(selectinload(Review.user))     # ✅ для ReviewUserBrief
        .order_by(order_func(sort_column), Review.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(items_query)).scalars().all()
    return list(items), total


async def get_product_summary(
    db: AsyncSession, product_id: int
) -> ReviewSummaryResponse:
    """
    Агрегат: avg_rating, total_count, distribution.

    При 0 отзывов: avg=0.0, total=0, distribution={1..5: 0}.
    """
    # Агрегат
    agg_query = select(
        func.avg(Review.rating),
        func.count(Review.id),
    ).where(
        Review.product_id == product_id,
        Review.deleted_at.is_(None),
    )
    avg_raw, total = (await db.execute(agg_query)).one()

    avg_rating = round(float(avg_raw), 2) if avg_raw is not None else 0.0

    # Distribution
    dist_query = (
        select(Review.rating, func.count(Review.id))
        .where(
            Review.product_id == product_id,
            Review.deleted_at.is_(None),
        )
        .group_by(Review.rating)
    )
    dist_rows = (await db.execute(dist_query)).all()

    # Все 5 ключей, даже если 0
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for rating, count in dist_rows:
        distribution[rating] = count

    return ReviewSummaryResponse(
        avg_rating=avg_rating,
        total_count=total,
        distribution=distribution,
    )


# ============================================================
#  Удаление
# ============================================================

async def get_review_by_public_id(
    db: AsyncSession, public_id
) -> Optional[Review]:
    """
    Возвращает отзыв по public_id, только если активный.

    Не фильтруем по user_id — вызывающий решает ownership.
    """
    result = await db.execute(
        select(Review)
        .where(
            Review.public_id == public_id,
            Review.deleted_at.is_(None),
        )
        .options(selectinload(Review.user))
    )
    return result.scalar_one_or_none()


async def soft_delete_review(db: AsyncSession, review: Review) -> None:
    """
    Soft-delete. Аудит сохраняется (deleted_at != NULL).

    И для юзера (свой отзыв), и для модератора (любой) —
    одна и та же функция. Различия в БД нет (осознанное
    решение 7-А: аудит важнее «чистоты» схемы).

    Партиальный UNIQUE (user_id, product_id) WHERE deleted_at IS NULL
    освобождает место — юзер может написать новый отзыв.
    """
    review.deleted_at = datetime.now(timezone.utc)
    await db.flush()


# ============================================================
#  Сериализация
# ============================================================

def serialize_review(review: Review) -> ReviewResponse:
    """Требует предзагруженного review.user через selectinload."""
    return ReviewResponse(
        public_id=review.public_id,
        product_id=review.product_id,
        user=ReviewUserBrief.model_validate(review.user),
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        is_verified=review.is_verified,
        created_at=review.created_at,
    )


# ============================================================
#  Внутренние утилиты
# ============================================================

async def _load_review(db: AsyncSession, review_id: int) -> Review:
    """Перезагрузка review со связями для сериализации."""
    result = await db.execute(
        select(Review)
        .where(Review.id == review_id)
        .options(selectinload(Review.user))
    )
    return result.scalar_one()


def _is_active_review_conflict(exc: IntegrityError) -> bool:
    """
    Проверяет, что IntegrityError — конфликт partial unique index
    на активный отзыв (user_id, product_id).
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False

    message = str(orig)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) if diag else None

    return (
        constraint_name == _ACTIVE_REVIEW_CONSTRAINT
        or _ACTIVE_REVIEW_CONSTRAINT in message
    )