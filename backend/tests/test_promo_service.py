# tests/test_promo_service.py
"""
Тесты promo_service: валидация, расчёт скидки, атомарный reserve.

Проверяют:
- happy path: валидный промокод → (promo, discount);
- все reason'ы ошибок (not_found, not_yet_active, expired, min_order_amount);
- расчёт для всех трёх типов скидки;
- округление ROUND_HALF_UP;
- fixed не превышает subtotal;
- reserve_promo_use инкрементирует при наличии лимита;
- reserve_promo_use возвращает False при исчерпанном лимите.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.db.enum import DiscountType
from app.models.promo_code import PromoCode
from app.services import promo_service
from app.services.promo_service import (
    _calculate_discount,
    reserve_promo_use,
    validate_and_calculate,
)
from fastapi import HTTPException
from sqlalchemy import select

# ============================================================
#  _calculate_discount — чистая математика
# ============================================================

class TestCalculateDiscount:
    """Проверяет формулу без БД."""

    def test_percentage_basic(self):
        p = SimpleNamespace(
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
        )
        assert _calculate_discount(p, Decimal("2150.00")) == Decimal("215.00")

    def test_percentage_round_half_up(self):
        """10.005 → 10.01 (ROUND_HALF_UP)."""
        p = SimpleNamespace(
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
        )
        assert _calculate_discount(p, Decimal("100.05")) == Decimal("10.01")

    def test_percentage_round_down_when_below_half(self):
        """10.004 → 10.00."""
        p = SimpleNamespace(
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
        )
        assert _calculate_discount(p, Decimal("100.04")) == Decimal("10.00")

    def test_fixed_less_than_subtotal(self):
        p = SimpleNamespace(
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("500.00"),
        )
        assert _calculate_discount(p, Decimal("1000.00")) == Decimal("500.00")

    def test_fixed_capped_at_subtotal(self):
        """Скидка 500 ₽ при сумме 300 ₽ → 300 ₽, не больше."""
        p = SimpleNamespace(
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("500.00"),
        )
        assert _calculate_discount(p, Decimal("300.00")) == Decimal("300.00")

    def test_fixed_equal_to_subtotal(self):
        p = SimpleNamespace(
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("500.00"),
        )
        assert _calculate_discount(p, Decimal("500.00")) == Decimal("500.00")

    def test_free_shipping_is_zero(self):
        """Стоимость доставки не считается → скидка 0."""
        p = SimpleNamespace(
            discount_type=DiscountType.FREE_SHIPPING,
            discount_value=Decimal("999.00"),
        )
        assert _calculate_discount(p, Decimal("1000.00")) == Decimal("0.00")


# ============================================================
#  validate_and_calculate — валидация через БД
# ============================================================

class TestValidateAndCalculate:
    """Валидация и расчёт с реальным PromoCode."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db_session, promo_code):
        promo, discount = await validate_and_calculate(
            db_session, "SUMMER10", Decimal("2150.00")
        )
        assert promo.id == promo_code.id
        assert discount == Decimal("215.00")

    @pytest.mark.asyncio
    async def test_not_found(self, db_session):
        with pytest.raises(HTTPException) as exc:
            await validate_and_calculate(
                db_session, "NOPE", Decimal("1000.00")
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "invalid_promo"
        assert exc.value.detail["reason"] == "not_found"
        assert exc.value.detail["promo_code"] == "NOPE"

    @pytest.mark.asyncio
    async def test_inactive_treated_as_not_found(
        self, db_session, promo_code
    ):
        promo_code.is_active = False
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await validate_and_calculate(
                db_session, "SUMMER10", Decimal("1000.00")
            )
        assert exc.value.detail["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_not_yet_active(self, db_session):
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="FUTURE",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            valid_from=now + timedelta(days=5),
            valid_until=now + timedelta(days=10),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await validate_and_calculate(
                db_session, "FUTURE", Decimal("1000.00")
            )
        assert exc.value.detail["reason"] == "not_yet_active"

    @pytest.mark.asyncio
    async def test_expired(self, db_session):
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="EXPIRED",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=1),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await validate_and_calculate(
                db_session, "EXPIRED", Decimal("1000.00")
            )
        assert exc.value.detail["reason"] == "expired"

    @pytest.mark.asyncio
    async def test_min_order_amount(self, db_session):
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="MIN5000",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            min_order_amount=Decimal("5000.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await validate_and_calculate(
                db_session, "MIN5000", Decimal("1000.00")
            )
        assert exc.value.detail["reason"] == "min_order_amount"
        assert exc.value.detail["min_order_amount"] == "5000.00"
        assert exc.value.detail["subtotal"] == "1000.00"

    @pytest.mark.asyncio
    async def test_min_order_amount_exactly_equal_ok(self, db_session):
        """subtotal == min_order_amount → ok (не «строго больше»)."""
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="MIN1000",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            min_order_amount=Decimal("1000.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        promo, discount = await validate_and_calculate(
            db_session, "MIN1000", Decimal("1000.00")
        )
        assert discount == Decimal("100.00")


# ============================================================
#  reserve_promo_use — атомарный инкремент
# ============================================================

class TestReservePromoUse:
    """Проверяет атомарный UPDATE used_count."""

    @pytest.mark.asyncio
    async def test_reserve_unlimited(self, db_session, promo_code):
        """max_uses=None → любой reserve проходит."""
        assert await reserve_promo_use(db_session, promo_code.id) is True
        await db_session.refresh(promo_code)
        assert promo_code.used_count == 1

        assert await reserve_promo_use(db_session, promo_code.id) is True
        await db_session.refresh(promo_code)
        assert promo_code.used_count == 2

    @pytest.mark.asyncio
    async def test_reserve_up_to_max_uses(self, db_session):
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="LIMITED",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_uses=2,
            used_count=0,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        assert await reserve_promo_use(db_session, p.id) is True
        assert await reserve_promo_use(db_session, p.id) is True
        # Третий — False (лимит исчерпан)
        assert await reserve_promo_use(db_session, p.id) is False

        await db_session.refresh(p)
        assert p.used_count == 2

    @pytest.mark.asyncio
    async def test_reserve_already_exhausted(self, db_session):
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="EXHAUSTED",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_uses=1,
            used_count=1,      # уже исчерпан
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        assert await reserve_promo_use(db_session, p.id) is False
        await db_session.refresh(p)
        assert p.used_count == 1   # не инкрементировался

    def test_percentage_capped_at_subtotal(self):
        """discount_value=150% при subtotal=1000 → discount=1000 (не 1500)."""
        p = SimpleNamespace(
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("150.00"),
        )
        assert _calculate_discount(p, Decimal("1000.00")) == Decimal("1000.00")

    def test_percentage_100_percent_is_subtotal(self):
        """discount_value=100% → discount=subtotal, total=0."""
        p = SimpleNamespace(
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("100.00"),
        )
        assert _calculate_discount(p, Decimal("1000.00")) == Decimal("1000.00")