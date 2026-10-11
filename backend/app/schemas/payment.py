# app/schemas/payment.py
"""
Схемы платежей.

PaymentResponse отдаёт public_id, а не внутренний id.
external_id — идентификатор платежа в платёжной системе (для идемпотентности).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.enum import PaymentMethod, PaymentStatus


class PaymentRequest(BaseModel):
    external_id: str | None = Field(
        default=None,
        max_length=255,
        description="ID платежа в шлюзе. Используется для идемпотентности.",
    )
    method: PaymentMethod

    model_config = ConfigDict(extra="forbid")


class PaymentResponse(BaseModel):
    public_id: UUID
    status: PaymentStatus
    amount: str          # Decimal → строка
    currency: str
    method: PaymentMethod
    external_id: str | None
    paid_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)