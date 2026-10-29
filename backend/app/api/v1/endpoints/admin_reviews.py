# app/api/v1/endpoints/admin_reviews.py
"""
Админские эндпоинты отзывов.

RBAC: require_roles(ADMIN, MODERATOR) — на уровне роутера.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.db.enum import UserRole
from app.db.session import get_db
from app.services import review_service

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/admin/reviews",
    tags=["admin:reviews"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)


# ============================================================
#  DELETE /admin/reviews/{public_id} — soft-delete любой
# ============================================================

@router.delete("/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review_admin(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete любого отзыва. Модерация постфактум.

    Не hard-delete — аудит сохраняется (deleted_at != NULL).
    404 если отзыв не найден.
    """
    review = await review_service.get_review_by_public_id(db, public_id)
    if review is None:
        raise HTTPException(404, "Review not found")

    await review_service.soft_delete_review(db, review)
    return None