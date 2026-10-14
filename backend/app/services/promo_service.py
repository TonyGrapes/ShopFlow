"""
Сервис промокодов.

Контракт:
- Валидация и расчёт скидки — без мутаций.
- Резерв использования (`used_count + 1`) — атомарный UPDATE,
  race-safe.
- Все ошибки валидации → 422 с детальным reason.

Reason'ы:
- not_found          — код не существует или is_active=False
- not_yet_active     — valid_from > now
- expired            — valid_until < now
- min_order_amount   — subtotal < min_order_amount
- max_uses_exceeded  — used_count >= max_uses (только reserve)
"""
import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enum import DiscountType
from app.models.promo_code import PromoCode

logger = logging.getLogger(__name__)


# ============================================================
#  Валидация и расчёт
# ============================================================

async def validate_and_calculate(
    db: AsyncSession,
    code: str,
    subtotal: Decimal,
) -> tuple[PromoCode, Decimal]:
    """
    Находит промокод, валидирует его и считает скидку.

    НЕ мутирует. Не резервирует used_count.
    Возвращает (promo, discount).

    Бросает 422 с детальным reason при любой проблеме.
    """
    promo = (await db.execute(
        select(PromoCode).where(PromoCode.code == code)
    )).scalar_one_or_none()

    if promo is None or not promo.is_active:
        _raise_invalid(code, "not_found")

    now = datetime.now(timezone.utc)
    if promo.valid_from > now:
        _raise_invalid(code, "not_yet_active")
    if promo.valid_until < now:
        _raise_invalid(code, "expired")
    if promo.min_order_amount is not None and subtotal < promo.min_order_amount:
        _raise_invalid(
            code,
            "min_order_amount",
            min_order_amount=str(promo.min_order_amount),
            subtotal=str(subtotal),
        )

    discount = _calculate_discount(promo, subtotal)
    return promo, discount


def _calculate_discount(promo: PromoCode, subtotal: Decimal) -> Decimal:
    """
    Считает скидку.

    - percentage:    subtotal * value / 100, ROUND_HALF_UP, 2 знака.
    - fixed:         min(value, subtotal) — скидка не может превысить сумму.
    - free_shipping: 0.00 (стоимость доставки у нас не считается).
    """
    if promo.discount_type == DiscountType.PERCENTAGE:
        return (subtotal * promo.discount_value / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    if promo.discount_type == DiscountType.FIXED:
        return min(promo.discount_value, subtotal).quantize(Decimal("0.01"))

    # FREE_SHIPPING
    return Decimal("0.00")


# ============================================================
#  Атомарный резерв использования
# ============================================================

async def reserve_promo_use(
    db: AsyncSession, promo_code_id: int
) -> bool:
    """
    Инкрементирует used_count + 1 атомарно, только если лимит не исчерпан.

    Возвращает True при успехе, False — если max_uses уже достигнут
    (гонка: кто-то опередил между validate_and_calculate и reserve).

    Атомарность: UPDATE ... WHERE (max_uses IS NULL OR used_count < max_uses)
    на уровне БД. rowcount = 0 → лимит исчерпан.
    """
    result = await db.execute(
        update(PromoCode)
        .where(
            PromoCode.id == promo_code_id,
            (PromoCode.max_uses.is_(None))
            | (PromoCode.used_count < PromoCode.max_uses),
        )
        .values(used_count=PromoCode.used_count + 1)
    )
    await db.flush()
    return (result.rowcount or 0) == 1


# ============================================================
#  Утилиты
# ============================================================

def _raise_invalid(code: str, reason: str, **extra) -> None:
    """Бросает 422 с единой структурой detail."""
    detail = {
        "code": "invalid_promo",
        "promo_code": code,
        "reason": reason,
    }
    detail.update(extra)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detail,
    )