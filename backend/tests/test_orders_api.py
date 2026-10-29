# tests/test_orders_api.py
"""
HTTP-тесты /api/v1/orders.

Проверяют:
- POST /orders — требует auth, создаёт заказ, очищает корзину;
- GET /orders — только свои, пагинация, фильтр по статусу;
- GET /orders/{public_id} — 404 для чужих;
- POST /orders/{public_id}/pay — оплата + идемпотентность.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enum import OrderStatus
from app.models.cart_item import CartItem
from app.models.order import Order

# ============================================================
#  POST /orders
# ============================================================

class TestCreateOrderEndpoint:
    """POST /api/v1/orders."""

    @pytest.mark.asyncio
    async def test_create_order_happy(
        self, client, auth_headers, address, product, cart_with_one_item
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.json()

        body = response.json()
        assert "public_id" in body
        assert body["status"] == "pending"
        assert Decimal(body["total"]) == Decimal("2000.00")
        assert len(body["items"]) == 1
        assert body["items"][0]["product_count"] == 2
        assert body["shipping_address"]["id"] == address.id

    @pytest.mark.asyncio
    async def test_create_order_without_token_401(
        self, client, address, cart_with_one_item
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_order_empty_cart_422(
        self, client, auth_headers, address
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "empty_cart"

    @pytest.mark.asyncio
    async def test_create_order_invalid_address_422(
        self, client, auth_headers, cart_with_one_item
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": 999999},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_address"

    @pytest.mark.asyncio
    async def test_create_order_foreign_address_422(
        self, client, auth_headers, address_for_admin, cart_with_one_item
    ):
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address_for_admin.id},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_address"

    @pytest.mark.asyncio
    async def test_create_order_out_of_stock_422(
        self, client, auth_headers, address, product, cart_with_one_item
    ):
        from app.db.enum import ProductStatus
        product.status = ProductStatus.OUTOFSTOCK

        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers=auth_headers,
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "cart_has_unavailable_items"
        assert len(body["errors"]) == 1

    @pytest.mark.asyncio
    async def test_create_order_clears_cart(
        self, client, db_session, auth_headers, verified_user,
        address, product, cart_with_one_item
    ):
        await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers=auth_headers,
        )

        # Корзина пуста
        cart_items = (await db_session.execute(
            select(CartItem).where(CartItem.user_id == verified_user.id)
        )).scalars().all()
        assert cart_items == []

    @pytest.mark.asyncio
    async def test_create_order_rejects_extra_fields(
        self, client, auth_headers, address, cart_with_one_item
    ):
        """extra='forbid' в OrderCreate."""
        response = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id, "hacker": "field"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_idempotent_replay(
        self, client, db_session, auth_headers, verified_user,
        address, cart_with_one_item,
    ):
        """Повтор с тем же Idempotency-Key и телом → тот же заказ."""
        r1 = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers={**auth_headers, "Idempotency-Key": "key-1"},
        )
        assert r1.status_code == 201, r1.json()
        pid1 = r1.json()["public_id"]

        r2 = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers={**auth_headers, "Idempotency-Key": "key-1"},
        )
        assert r2.status_code == 201
        pid2 = r2.json()["public_id"]
        assert pid1 == pid2

        orders = (await db_session.execute(
            select(Order).where(Order.user_id == verified_user.id)
        )).scalars().all()
        assert len(orders) == 1


    @pytest.mark.asyncio
    async def test_create_order_idempotency_key_reused_with_different_body(
        self, client, auth_headers, address, address_for_admin,
        cart_with_one_item,
    ):
        """Тот же ключ, другое тело → 409."""
        r1 = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers={**auth_headers, "Idempotency-Key": "key-2"},
        )
        assert r1.status_code == 201

        r2 = await client.post(
            "/api/v1/orders",
            json={"address_id": address_for_admin.id},
            headers={**auth_headers, "Idempotency-Key": "key-2"},
        )
        assert r2.status_code == 409
        assert r2.json()["code"] == "idempotency_key_reused"


    @pytest.mark.asyncio
    async def test_create_order_without_idempotency_key_works(
        self, client, auth_headers, address, cart_with_one_item
    ):
        """Без Idempotency-Key — 201, как было."""
        r = await client.post(
            "/api/v1/orders",
            json={"address_id": address.id},
            headers=auth_headers,
        )
        assert r.status_code == 201


# ============================================================
#  GET /orders
# ============================================================

class TestListOrdersEndpoint:
    """GET /api/v1/orders."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client, auth_headers):
        response = await client.get("/api/v1/orders", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_list_returns_only_my(
        self, client, auth_headers, order, db_session, admin_user, address
    ):
        """Заказ admin_user не виден в списке verified_user."""
        from decimal import Decimal as D

        other = Order(
            user_id=admin_user.id,
            total=D("100.00"),
            status=OrderStatus.PENDING,
            shipping_address_id=address.id,
        )
        db_session.add(other)
        await db_session.flush()

        response = await client.get("/api/v1/orders", headers=auth_headers)
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["public_id"] == str(order.public_id)

    @pytest.mark.asyncio
    async def test_list_pagination(
        self, client, auth_headers, verified_user, address, db_session
    ):
        from decimal import Decimal as D
        for i in range(5):
            db_session.add(Order(
                user_id=verified_user.id,
                total=D(f"{100 + i}.00"),
                status=OrderStatus.PENDING,
                shipping_address_id=address.id,
            ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/orders?page=1&page_size=2", headers=auth_headers
        )
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(
        self, client, auth_headers, order, paid_order
    ):
        response = await client.get(
            "/api/v1/orders?status=paid", headers=auth_headers
        )
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "paid"

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        response = await client.get("/api/v1/orders")
        assert response.status_code == 401


# ============================================================
#  GET /orders/{public_id}
# ============================================================

class TestGetOrderEndpoint:
    """GET /api/v1/orders/{public_id}."""

    @pytest.mark.asyncio
    async def test_get_own_order(self, client, auth_headers, order):
        response = await client.get(
            f"/api/v1/orders/{order.public_id}", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["public_id"] == str(order.public_id)
        assert len(body["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_foreign_order_404(
        self, client, auth_headers, db_session, admin_user, address, product
    ):
        """Чужой заказ → 404, не 403."""
        from decimal import Decimal as D

        other = Order(
            user_id=admin_user.id,
            total=D("500.00"),
            status=OrderStatus.PENDING,
            shipping_address_id=address.id,
        )
        db_session.add(other)
        await db_session.flush()

        response = await client.get(
            f"/api/v1/orders/{other.public_id}", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_missing_404(self, client, auth_headers):
        """Невалидный/несуществующий UUID → 404."""
        response = await client.get(
            "/api/v1/orders/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert response.status_code == 404


# ============================================================
#  POST /orders/{public_id}/pay
# ============================================================

class TestPayOrderEndpoint:
    """POST /api/v1/orders/{public_id}/pay."""

    @pytest.mark.asyncio
    async def test_pay_pending_order(
        self, client, auth_headers, order, db_session
    ):
        response = await client.post(
            f"/api/v1/orders/{order.public_id}/pay",
            json={"external_id": "ext-api-1", "method": "card"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.json()

        body = response.json()
        assert body["external_id"] == "ext-api-1"
        assert body["status"] == "completed"
        assert Decimal(body["amount"]) == order.total

        # Проверяем статус order
        await db_session.refresh(order)
        assert order.status == OrderStatus.PAID

    @pytest.mark.asyncio
    async def test_pay_idempotent_replay(
        self, client, auth_headers, order
    ):
        """Повторный pay с тем же external_id → 200, тот же Payment."""
        r1 = await client.post(
            f"/api/v1/orders/{order.public_id}/pay",
            json={"external_id": "ext-api-replay", "method": "card"},
            headers=auth_headers,
        )
        assert r1.status_code == 200
        pid1 = r1.json()["public_id"]

        r2 = await client.post(
            f"/api/v1/orders/{order.public_id}/pay",
            json={"external_id": "ext-api-replay", "method": "card"},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        pid2 = r2.json()["public_id"]
        assert pid1 == pid2

    @pytest.mark.asyncio
    async def test_pay_canceled_order_422(
        self, client, auth_headers, order, db_session
    ):
        order.status = OrderStatus.CANCELED
        await db_session.flush()

        response = await client.post(
            f"/api/v1/orders/{order.public_id}/pay",
            json={"external_id": "ext-x", "method": "card"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "order_canceled"

    @pytest.mark.asyncio
    async def test_pay_foreign_order_404(
        self, client, auth_headers, db_session, admin_user, address
    ):
        from decimal import Decimal as D
        other = Order(
            user_id=admin_user.id,
            total=D("100.00"),
            status=OrderStatus.PENDING,
            shipping_address_id=address.id,
        )
        db_session.add(other)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/orders/{other.public_id}/pay",
            json={"external_id": "ext-x", "method": "card"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pay_requires_auth(self, client, order):
        response = await client.post(
            f"/api/v1/orders/{order.public_id}/pay",
            json={"external_id": "ext-x", "method": "card"},
        )
        assert response.status_code == 401
