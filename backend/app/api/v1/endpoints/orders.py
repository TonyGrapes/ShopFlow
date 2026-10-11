# app/api/v1/endpoints/orders.py
"""
Пользовательские эндпоинты заказов.

Контракт:
- Создание заказа — из корзины, атомарно.
- Чужие заказы → 404 (не 403), чтобы не раскрывать существование.
- Публичный идентификатор заказа — public_id (UUID).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import User, get_current_active_user
from app.db.enum import OrderStatus
from app.db.session import get_db
from app.schemas.common import Paginated
from app.schemas.order import (
    OrderCreate,
    OrderListItem,
    OrderResponse,
)
from app.schemas.payment import PaymentRequest, PaymentResponse
from app.services import order_service, payment_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])


# ============================================================
#  POST /orders — создать заказ из корзины
# ============================================================

@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    data: OrderCreate,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Создаёт заказ из корзины юзера.

    Требует:
    - активного юзера (401 для гостя, 403 для бан/pending-verify),
    - непустой корзины (422),
    - валидного address_id, принадлежащего юзеру (422),
    - всех товаров в статусе available (422 со списком).

    Корзина очищается в той же транзакции. При ошибке — не очищается.
    """
    order = await order_service.create_order_from_cart(
        db=db,
        user=current.orm,
        address_id=data.address_id,
    )
    return order_service.serialize_order(order)


# ============================================================
#  GET /orders — мои заказы
# ============================================================

@router.get("", response_model=Paginated[OrderListItem])
async def list_my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Заказы юзера. Пагинация + опциональный фильтр по статусу."""
    orders, total = await order_service.get_user_orders(
        db=db,
        user_id=current.id,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )
    return Paginated[OrderListItem](
        items=[order_service.serialize_order_list_item(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
#  GET /orders/{public_id} — детали
# ============================================================

@router.get("/{public_id}", response_model=OrderResponse)
async def get_order(
    public_id: str,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Детали заказа. 404 для чужих — не раскрываем существование.
    """
    order = await order_service.get_order_detail(
        db=db,
        user_id=current.id,
        order_public_id=public_id,
    )
    if order is None:
        raise HTTPException(404, "Order not found")
    return order_service.serialize_order(order)


# ============================================================
#  POST /orders/{public_id}/pay — mock-оплата
# ============================================================

@router.post("/{public_id}/pay", response_model=PaymentResponse)
async def pay_order(
    public_id: str,
    data: PaymentRequest,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mock-оплата заказа.

    Идемпотентно по external_id: повторный вызов с тем же
    external_id возвращает существующий Payment (200).

    Ошибки:
    - 404: чужой/несуществующий заказ,
    - 409: external_id занят другим заказом,
    - 422: заказ canceled/shipped/delivered (нельзя оплатить).
    """
    order = await order_service.get_order_detail(
        db=db,
        user_id=current.id,
        order_public_id=public_id,
    )
    if order is None:
        raise HTTPException(404, "Order not found")

    payment = await payment_service.process_payment(
        db=db,
        order=order,
        external_id=data.external_id,
        method=data.method,
    )
    return payment_service.serialize_payment(payment)