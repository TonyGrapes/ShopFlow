"""
Схемы возвратов.

RefundResponse отдаёт public_id (UUID), не внутренний id.
external_id — идентификатор возврата в платёжном шлюзе
(для идемпотентности, как у Payment).

reason — enum-строка: customer_request | defective | wrong_item | other.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.enum import RefundStatus
from app.schemas.common import Money

# ============================================================
#  Create
# ============================================================

class RefundCreate(BaseModel):
    amount: Money = Field(
        gt=0,
        description="Сумма возврата. Не больше остатка по платежу.",
    )
    reason: str | None = Field(
        default=None,
        description="Причина: customer_request | defective | wrong_item | other",
    )
    external_id: str | None = Field(
        default=None,
        max_length=255,
        description="ID возврата в шлюзе. Для идемпотентности.",
    )

    model_config = ConfigDict(extra="forbid")


# ============================================================
#  Response
# ============================================================

class RefundResponse(BaseModel):
    public_id: UUID
    payment_id: int
    amount: Money
    reason: str | None
    status: RefundStatus
    external_id: str | None
    refunded_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)