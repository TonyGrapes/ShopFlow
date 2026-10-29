# app/api/v1/endpoints/admin_orders.py
"""
Админские эндпоинты заказов.

RBAC: require_roles(ADMIN, MODERATOR) — на уровне роутера.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.db.enum import OrderStatus, UserRole
from app.db.session import get_db
from app.schemas.common import Paginated
from app.schemas.order import (
    OrderListItem,
    OrderResponse,
    OrderStatusUpdate,
)
from app.services import order_service

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/admin/orders",
    tags=["admin:orders"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)


# ============================================================
#  GET /admin/orders — все заказы
# ============================================================

@router.get("", response_model=Paginated[OrderListItem])
async def list_all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: OrderStatus | None = Query(None, alias="status"),
    user_id: int | None = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Все заказы с фильтрами. Сортировка по created_at DESC.

    Фильтр user_id — по внутреннему id (админ знает id, публичный UUID
    не обязателен в admin API).
    """
    orders, total = await order_service.list_orders_admin(
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        user_id=user_id,
    )
    return Paginated[OrderListItem](
        items=[order_service.serialize_order_list_item(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
#  GET /admin/orders/{public_id}
# ============================================================

@router.get("/{public_id}", response_model=OrderResponse)
async def get_order_admin(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Детали любого заказа."""
    order = await order_service.get_order_for_admin(db, public_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    return order_service.serialize_order(order)


# ============================================================
#  PATCH /admin/orders/{public_id}/status
# ============================================================

@router.patch("/{public_id}/status", response_model=OrderResponse)
async def update_order_status(
    public_id: str,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Смена статуса. Валидация переходов в сервисе.

    Ошибки:
    - 404: заказ не найден,
    - 422: недопустимый переход (например, delivered → paid).
    """
    order = await order_service.get_order_for_admin(db, public_id)
    if order is None:
        raise HTTPException(404, "Order not found")

    await order_service.update_order_status(db, order, data.status)

    # ✅ Перечитываем после UPDATE: flush мог expire-нуть updated_at
    #    (server-side onupdate) — sync-обращение дало бы MissingGreenlet.
    #    Заодно подтягиваем актуальные items/payments со свежим статусом.
    order = await order_service.get_order_for_admin(db, public_id)
    if order is None:
        # Теоретически не может быть: заказ был секунду назад.
        raise HTTPException(404, "Order not found")

    return order_service.serialize_order(order)