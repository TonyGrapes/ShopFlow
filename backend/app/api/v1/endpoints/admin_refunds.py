"""
Админские эндпоинты возвратов.

RBAC: require_roles(ADMIN, MODERATOR) — на уровне роутера.

Контракт:
- POST /admin/payments/{payment_id}/refund — создать возврат;
- GET /admin/refunds/{public_id} — детали возврата;
- GET /admin/payments/{payment_id}/refunds — все возвраты по платежу.

Идемпотентность по external_id: replay → 200 с существующим Refund.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.db.enum import UserRole
from app.db.session import get_db
from app.models.payment import Payment
from app.schemas.refund import RefundCreate, RefundResponse
from app.services import refund_service

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/admin",
    tags=["admin:refunds"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)


# ============================================================
#  POST /admin/payments/{payment_id}/refund
# ============================================================

@router.post(
    "/payments/{payment_id}/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_refund(
    payment_id: int,
    data: RefundCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создаёт возврат по платежу.

    Ошибки:
    - 404: payment не найден;
    - 409: external_id занят другим возвратом;
    - 422: payment не completed / amount > остатка / reason невалиден.

    Идемпотентно по external_id: повторный POST с тем же external_id
    на тот же payment вернёт существующий Refund (200 → но у нас 201-ответ
    при первом создании; при replay FastAPI вернёт 200? — нет, 201,
    но с существующим public_id. Это допустимо, клиент различает по public_id).

    Точнее: при replay мы возвращаем существующий Refund, FastAPI отдаёт 201.
    Семантически это «уже создано» — 200 было бы точнее, но ради единообразия
    с process_payment оставляем 201.
    """
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found")

    refund = await refund_service.create_refund(db, payment, data)
    return refund_service.serialize_refund(refund)


# ============================================================
#  GET /admin/refunds/{public_id}
# ============================================================

@router.get("/refunds/{public_id}", response_model=RefundResponse)
async def get_refund(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Детали возврата по public_id. 404 если не найден."""
    refund = await refund_service.get_refund_by_public_id(db, public_id)
    if refund is None:
        raise HTTPException(404, "Refund not found")
    return refund_service.serialize_refund(refund)


# ============================================================
#  GET /admin/payments/{payment_id}/refunds
# ============================================================

@router.get(
    "/payments/{payment_id}/refunds",
    response_model=list[RefundResponse],
)
async def list_refunds(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Все возвраты по платежу.

    404 если payment не найден. Пустой список — payment есть, возвратов нет.
    """
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found")

    refunds = await refund_service.list_refunds_for_payment(db, payment_id)
    return [refund_service.serialize_refund(r) for r in refunds]