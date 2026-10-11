# app/schemas/order.py
"""
Схемы заказов.

OrderResponse отдаёт public_id (UUID), не внутренний id.
OrderListItem — облегчённая версия без items (для списка).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.enum import OrderStatus, ProductStatus
from app.schemas.address import AddressBrief
from app.schemas.common import Money
from app.schemas.payment import PaymentResponse

# ============================================================
#  Create
# ============================================================

class OrderCreate(BaseModel):
    address_id: int = Field(gt=0, description="ID адреса доставки (должен принадлежать юзеру)")

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
    """Позиция заказа. product_cost — snapshot цены на момент заказа."""
    public_id: UUID
    product: OrderItemProductBrief
    product_cost: Money
    product_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    public_id: UUID
    status: OrderStatus
    total: Money
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