# app/schemas/order.py
"""
Схемы заказов.

OrderResponse отдаёт public_id (UUID), не внутренний id.
OrderListItem — облегчённая версия без items/payments (для списка).
subtotal — computed field, не хранится в БД.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.db.enum import OrderStatus, ProductStatus
from app.schemas.address import AddressBrief
from app.schemas.common import Money
from app.schemas.payment import PaymentResponse

# ============================================================
#  Create
# ============================================================

class OrderCreate(BaseModel):
    address_id: int = Field(
        gt=0,
        description="ID адреса доставки (должен принадлежать текущему юзеру)",
    )
    promo_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Промокод. Валидируется повторно в момент оформления.",
    )

    model_config = ConfigDict(extra="forbid")


# ============================================================
#  Response
# ============================================================

class OrderItemProductBrief(BaseModel):
    """Продукт внутри позиции заказа. Публичный id, имя, обложка."""
    id: int
    name: str
    cover_url: str | None = None
    status: ProductStatus

    model_config = ConfigDict(from_attributes=True)


class OrderItemResponse(BaseModel):
    """
    Позиция заказа.

    product_cost — snapshot цены на момент оформления заказа.
    product_count — количество (в модели OrderItem поле называется
    именно так, в отличие от CartItem.quantity).
    """
    public_id: UUID
    product: OrderItemProductBrief
    product_cost: Money
    product_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    """
    Полный заказ.

    subtotal — computed: sum(items.product_cost * items.product_count).
    discount_amount — NULL если промокода не было.
    total — финальная сумма после скидки.
    """
    public_id: UUID
    status: OrderStatus
    subtotal: Money                    # ← заполняется вручную в serialize_order
    discount_amount: Money | None
    total: Money
    promo_code: str | None
    shipping_address: AddressBrief
    items: list[OrderItemResponse]
    payments: list[PaymentResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderListItem(BaseModel):
    """Облегчённая карточка для списка. Без items и payments."""
    public_id: UUID
    status: OrderStatus
    discount_amount: Money | None
    total: Money
    items_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
#  Admin
# ============================================================

class OrderStatusUpdate(BaseModel):
    status: OrderStatus

    model_config = ConfigDict(extra="forbid")