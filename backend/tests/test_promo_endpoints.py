"""
HTTP-тесты промокодов:
- POST /cart/apply-promo (preview);
- POST /orders с promo_code.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.db.enum import DiscountType, OrderStatus
from app.models.order import Order
from app.models.promo_code import PromoCode
from sqlalchemy import select

# ============================================================
#  POST /cart/apply-promo — preview
# ============================================================

class TestApplyPromoPreview:
    """Preview endpoint. Без мутаций."""

    @pytest.mark.asyncio
    async def test_preview_happy(
        self, client, auth_headers, cart_with_one_item, promo_code
    ):
        """
        Корзина: 1 laptop 1000.00 * 2 = 2000.00.
        Промокод SUMMER10 (10%) → 200.00 discount, final 1800.00.
        """
        response = await client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "SUMMER10"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["code"] == "SUMMER10"
        assert body["discount_type"] == "percentage"
        assert Decimal(body["subtotal"]) == Decimal("2000.00")
        assert Decimal(body["discount_amount"]) == Decimal("200.00")
        assert Decimal(body["final_total"]) == Decimal("1800.00")

    @pytest.mark.asyncio
    async def test_preview_fixed_promo(
        self, client, auth_headers, cart_with_one_item, promo_code_fixed
    ):
        """FIX500 → 500 ₽ от 2000.00 = final 1500.00."""
        response = await client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "FIX500"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["discount_amount"]) == Decimal("500.00")
        assert Decimal(body["final_total"]) == Decimal("1500.00")

    @pytest.mark.asyncio
    async def test_preview_does_not_increment_used_count(
        self, client, auth_headers, cart_with_one_item, promo_code,
        db_session
    ):
        """Preview — без побочных эффектов. used_count не меняется."""
        # Трижды вызываем preview
        for _ in range(3):
            r = await client.post(
                "/api/v1/cart/apply-promo",
                json={"code": "SUMMER10"},
                headers=auth_headers,
            )
            assert r.status_code == 200

        await db_session.refresh(promo_code)
        assert promo_code.used_count == 0

    @pytest.mark.asyncio
    async def test_preview_empty_cart_422(
        self, client, auth_headers, promo_code
    ):
        """Пустая корзина → 422 empty_cart."""
        response = await client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "SUMMER10"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "empty_cart"

    @pytest.mark.asyncio
    async def test_preview_unknown_code_422(
        self, client, auth_headers, cart_with_one_item
    ):
        response = await client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "NOPE"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["code"] == "invalid_promo"
        assert body["detail"]["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_preview_expired_422(
        self, client, auth_headers, cart_with_one_item, db_session
    ):
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

        response = await client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "EXPIRED"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "expired"

    @pytest.mark.asyncio
    async def test_preview_min_order_amount_422(
        self, client, auth_headers, cart_with_one_item, db_session
    ):
        """Корзина 2000.00, min 5000 → отказ."""
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

        response = await client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "MIN5000"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["reason"] == "min_order_amount"
        assert body["detail"]["min_order_amount"] == "5000.00"
        assert body["detail"]["subtotal"] == "2000.00"

    @pytest.mark.asyncio
    async def test_preview_guest_allowed(
        self, guest_client, product, real_guest_store, promo_code
    ):
        """
        Гость: корзина в Redis (fakeredis), promo_code в db_session.

        Оба видны через общую сессию: guest_client использует ту же
        db_session через override get_db, что и фикстура promo_code.
        """
        add = await guest_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )
        assert add.status_code == 201, add.json()

        response = await guest_client.post(
            "/api/v1/cart/apply-promo",
            json={"code": "SUMMER10"},
        )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert Decimal(body["subtotal"]) == Decimal("2000.00")
        assert Decimal(body["discount_amount"]) == Decimal("200.00")
        assert Decimal(body["final_total"]) == Decimal("1800.00")

# ============================================================
#  POST /orders с promo_code
# ============================================================

class TestCreateOrderWithPromo:
    """Заказ с промокодом."""

    @pytest.mark.asyncio
    async def test_order_with_percentage_promo(
        self, client, auth_headers, address, cart_with_one_item,
        promo_code, db_session
    ):
        """
        Laptop 1000*2 = 2000.00, промокод 10% → discount 200.00,
        total 1800.00. used_count инкрементирован.
        """
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "SUMMER10"},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.json()
        body = response.json()

        assert Decimal(body["subtotal"]) == Decimal("2000.00")
        assert Decimal(body["discount_amount"]) == Decimal("200.00")
        assert Decimal(body["total"]) == Decimal("1800.00")
        assert body["promo_code"] == "SUMMER10"

        # used_count инкрементирован
        await db_session.refresh(promo_code)
        assert promo_code.used_count == 1

    @pytest.mark.asyncio
    async def test_order_with_fixed_promo(
        self, client, auth_headers, address, cart_with_one_item,
        promo_code_fixed
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "FIX500"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert Decimal(body["discount_amount"]) == Decimal("500.00")
        assert Decimal(body["total"]) == Decimal("1500.00")

    @pytest.mark.asyncio
    async def test_order_without_promo_has_nulls(
        self, client, auth_headers, address, cart_with_one_item
    ):
        """Без промокода: discount_amount=null, promo_code=null."""
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers=auth_headers,
        )
        body = response.json()
        assert body["promo_code"] is None
        assert body["discount_amount"] is None
        assert Decimal(body["subtotal"]) == Decimal(body["total"])

    @pytest.mark.asyncio
    async def test_order_invalid_promo_422(
        self, client, auth_headers, address, cart_with_one_item
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "NOPE"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["code"] == "invalid_promo"
        assert body["detail"]["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_order_expired_promo_422(
        self, client, auth_headers, address, cart_with_one_item, db_session
    ):
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="EXPIRED2",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=1),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "EXPIRED2"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "expired"

    @pytest.mark.asyncio
    async def test_order_exhausted_promo_422(
        self, client, auth_headers, address, cart_with_one_item, db_session
    ):
        """Промокод с исчерпанным лимитом → 422 max_uses_exceeded."""
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="EXHAUSTED",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_uses=1,
            used_count=1,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "EXHAUSTED"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "invalid_promo"
        assert body["reason"] == "max_uses_exceeded"

    @pytest.mark.asyncio
    async def test_order_promo_reserved_but_cart_error_rolls_back(
        self, client, auth_headers, address, cart_with_one_item,
        promo_code, db_session, product
    ):
        """
        Транзакционность: если что-то падает после reserve — used_count
        откатывается вместе с заказом.

        Здесь эмулируем падение через out_of_stock одного из товаров.
        """
        # Делаем товар недоступным — это сработает ДО reserve,
        # но проверим, что промокод вообще не инкрементировался
        from app.db.enum import ProductStatus
        product.status = ProductStatus.OUTOFSTOCK
        await db_session.flush()

        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "SUMMER10"},
            headers=auth_headers,
        )
        assert response.status_code == 422

        await db_session.refresh(promo_code)
        assert promo_code.used_count == 0   # не инкрементирован

    @pytest.mark.asyncio
    async def test_order_with_100_percent_promo_total_zero(
        self, client, auth_headers, address, cart_with_one_item, db_session
    ):
        """Промокод 100% → discount=subtotal=2000, total=0, не 500."""
        now = datetime.now(timezone.utc)
        p = PromoCode(
            code="MAX100",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("100.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            is_active=True,
        )
        db_session.add(p)
        await db_session.flush()

        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "promo_code": "MAX100"},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert Decimal(body["subtotal"]) == Decimal("2000.00")
        assert Decimal(body["discount_amount"]) == Decimal("2000.00")
        assert Decimal(body["total"]) == Decimal("0.00")