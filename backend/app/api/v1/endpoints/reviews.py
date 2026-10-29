# app/api/v1/endpoints/reviews.py
"""
Отзывы: публичные (read) + пользовательские (write).

Публичные:
- GET  /products/{product_id}/reviews         — список (пагинация, сортировка)
- GET  /products/{product_id}/reviews/summary — агрегат

Пользовательские (auth):
- POST   /reviews              — создать (только после delivered-заказа)
- DELETE /reviews/{public_id}  — soft-delete свой
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import User, get_current_active_user
from app.db.session import get_db
from app.schemas.common import Paginated
from app.schemas.review import (
    ReviewCreate,
    ReviewResponse,
    ReviewSummaryResponse,
)
from app.services import review_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reviews"])


# ============================================================
#  GET /products/{product_id}/reviews — список
# ============================================================

@router.get(
    "/products/{product_id}/reviews",
    response_model=Paginated[ReviewResponse],
)
async def list_product_reviews(
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at", pattern="^(created_at|rating)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Публичный список активных отзывов товара.

    Soft-deleted исключены. Сортировка: created_at (default, desc) или rating.
    """
    items, total = await review_service.list_product_reviews(
        db=db,
        product_id=product_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return Paginated[ReviewResponse](
        items=[review_service.serialize_review(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
#  GET /products/{product_id}/reviews/summary — агрегат
# ============================================================

@router.get(
    "/products/{product_id}/reviews/summary",
    response_model=ReviewSummaryResponse,
)
async def get_product_reviews_summary(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Агрегат: avg_rating, total_count, distribution {1..5}.

    При 0 отзывов: avg=0.0, total=0, distribution={1:0..5:0}.
    """
    return await review_service.get_product_summary(db, product_id)


# ============================================================
#  POST /reviews — создание
# ============================================================

@router.post(
    "/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    data: ReviewCreate,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Создаёт отзыв.

    Требует:
    - auth (401 для гостя),
    - товар существует (404),
    - delivered-заказ с этим товаром (403),
    - нет активного отзыва (409).
    """
    review = await review_service.create_review(db, current.orm, data)
    return review_service.serialize_review(review)


# ============================================================
#  DELETE /reviews/{public_id} — soft-delete свой
# ============================================================

@router.delete(
    "/reviews/{public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_own_review(
    public_id: str,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete свой отзыв.

    404 — если отзыв не найден ИЛИ принадлежит другому юзеру.
    (404 вместо 403 — не раскрываем существование чужого отзыва.)
    """
    review = await review_service.get_review_by_public_id(db, public_id)
    if review is None or review.user_id != current.id:
        raise HTTPException(404, "Review not found")

    await review_service.soft_delete_review(db, review)
    return None