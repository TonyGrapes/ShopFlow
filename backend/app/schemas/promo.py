# app/schemas/promo.py
"""
Схемы промокодов.

Только preview — админский CRUD промокодов вне скоупа этого эпика.
"""
from pydantic import BaseModel, ConfigDict, Field

from app.db.enum import DiscountType
from app.schemas.common import Money


class PromoCodePreviewRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")


class PromoCodePreviewResponse(BaseModel):
    """
    Результат preview. Без сохранения — только расчёт.

    Клиент показывает subtotal → discount → final_total.
    """
    code: str
    discount_type: DiscountType
    discount_value: str      # Decimal → строка
    subtotal: Money
    discount_amount: Money
    final_total: Money