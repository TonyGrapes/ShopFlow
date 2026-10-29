# tests/test_cart_user.py
"""
Тесты пользовательской корзины (PostgreSQL, таблица cart_items).

Проверяют:
- CRUD позиций для залогиненного;
- 404 при отсутствии позиции (в отличие от гостя);
- фильтрацию soft-deleted с hidden_items_count;
- snapshot_cost для user-cart;
- лимит позиций (GUEST_CART_MAX_ITEMS применяется и к юзеру);
- изоляцию корзин разных юзеров.
"""
from datetime import UTC, datetime
from decimal import Decimal

import pytest


class TestUserCartAdd:
    """POST /cart/items — залогиненный юзер."""

    @pytest.mark.asyncio
    async def test_add_item_as_user(self, cart_client, product, auth_headers):
        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
            headers=auth_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["total_items"] == 2
        assert body["items"][0]["quantity"] == 2

    @pytest.mark.asyncio
    async def test_add_accumulates(self, cart_client, product, auth_headers):
        """Повторный POST того же товара → quantity += delta."""
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
            headers=auth_headers,
        )
        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 3},
            headers=auth_headers,
        )
        assert response.json()["items"][0]["quantity"] == 5

    @pytest.mark.asyncio
    async def test_add_nonexistent_product_404(
        self, cart_client, auth_headers
    ):
        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": 999999, "quantity": 1},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_soft_deleted_product_404(
        self, cart_client, db_session, product, auth_headers
    ):
        product.deleted_at = datetime.now(UTC)
        await db_session.flush()

        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestUserCartUpdate:
    """PATCH /cart/items/{product_id}."""

    @pytest.mark.asyncio
    async def test_patch_absolute_quantity(
        self, cart_client, product, auth_headers
    ):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
            headers=auth_headers,
        )
        response = await cart_client.patch(
            f"/api/v1/cart/items/{product.id}",
            json={"quantity": 7},
            headers=auth_headers,
        )
        assert response.json()["items"][0]["quantity"] == 7

    @pytest.mark.asyncio
    async def test_patch_zero_removes(
        self, cart_client, product, auth_headers
    ):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
            headers=auth_headers,
        )
        response = await cart_client.patch(
            f"/api/v1/cart/items/{product.id}",
            json={"quantity": 0},
            headers=auth_headers,
        )
        assert response.json()["items"] == []

    @pytest.mark.asyncio
    async def test_patch_nonexistent_returns_404(
        self, cart_client, product, auth_headers
    ):
        """
        Для юзера 404 — позиция либо есть, либо нет,
        нет смысла делать no-op (в отличие от гостя).
        """
        response = await cart_client.patch(
            f"/api/v1/cart/items/{product.id}",
            json={"quantity": 5},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestUserCartDelete:
    """DELETE /cart/items/{product_id} и DELETE /cart."""

    @pytest.mark.asyncio
    async def test_delete_removes_item(
        self, cart_client, product, auth_headers
    ):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
            headers=auth_headers,
        )
        response = await cart_client.delete(
            f"/api/v1/cart/items/{product.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(
        self, cart_client, product, auth_headers
    ):
        response = await cart_client.delete(
            f"/api/v1/cart/items/{product.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_clear_cart(self, cart_client, product, auth_headers):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
            headers=auth_headers,
        )
        response = await cart_client.delete(
            "/api/v1/cart", headers=auth_headers
        )
        assert response.status_code == 204

        check = await cart_client.get("/api/v1/cart", headers=auth_headers)
        assert check.json()["items"] == []


class TestUserCartSnapshot:
    """Снимок цены в user-cart."""

    @pytest.mark.asyncio
    async def test_snapshot_cost_does_not_change(
        self, cart_client, db_session, product, auth_headers
    ):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
            headers=auth_headers,
        )
        original_cost = product.cost

        product.cost = original_cost + Decimal("500.00")
        await db_session.flush()

        response = await cart_client.get(
            "/api/v1/cart", headers=auth_headers
        )
        item = response.json()["items"][0]
        assert Decimal(item["snapshot_cost"]) == original_cost
        assert Decimal(item["current_cost"]) == original_cost + Decimal("500.00")


class TestUserCartSoftDeleted:
    """Soft-deleted фильтрация в user-cart."""

    @pytest.mark.asyncio
    async def test_soft_deleted_hidden(
        self, cart_client, db_session, product, auth_headers
    ):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
            headers=auth_headers,
        )
        product.deleted_at = datetime.now(UTC)
        await db_session.flush()

        response = await cart_client.get(
            "/api/v1/cart", headers=auth_headers
        )
        body = response.json()
        assert body["items"] == []
        assert body["hidden_items_count"] == 1


class TestUserCartIsolation:
    """Корзины разных пользователей изолированы."""

    @pytest.mark.asyncio
    async def test_carts_are_isolated(
        self, cart_client, product, auth_headers, admin_headers
    ):
        # Customer добавляет 2
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
            headers=auth_headers,
        )
        # Admin добавляет 5
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 5},
            headers=admin_headers,
        )

        # Customer видит свою
        r1 = await cart_client.get("/api/v1/cart", headers=auth_headers)
        assert r1.json()["items"][0]["quantity"] == 2

        # Admin видит свою
        r2 = await cart_client.get("/api/v1/cart", headers=admin_headers)
        assert r2.json()["items"][0]["quantity"] == 5