# tests/test_cart_guest.py
"""
Тесты гостевой корзины (Redis + cookie shopflow_cart_session).

Проверяют:
- создание guest session при первом запросе;
- идемпотентный upsert (повторный POST — quantity += delta);
- PATCH абсолютного количества и удаление;
- DELETE позиции;
- фильтрацию soft-deleted товаров с hidden_items_count;
- снимок цены snapshot_cost — не меняется при изменении cost товара;
- 404 для несуществующего товара;
- отсутствие двойного учёта при PATCH несуществующей позиции (no-op).
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.models.product import Product


class TestGuestCartAdd:
    """POST /cart/items — гость без авторизации."""

    @pytest.mark.asyncio
    async def test_add_item_creates_session_and_returns_cart(
        self, cart_client, product
    ):
        """Первый POST создаёт cookie shopflow_cart_session и позицию в Redis."""
        s = get_settings()

        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["total_items"] == 2
        assert len(body["items"]) == 1

        item = body["items"][0]
        assert item["product_id"] == product.id
        assert item["quantity"] == 2
        # Первое добавление — snapshot == current
        assert Decimal(item["snapshot_cost"]) == product.cost
        assert Decimal(item["current_cost"]) == product.cost
        assert item["is_available"] is True
        assert body["hidden_items_count"] == 0

        # ✅ Cookie guest session установлена
        assert s.GUEST_CART_COOKIE_NAME in cart_client.cookies

    @pytest.mark.asyncio
    async def test_add_same_product_accumulates(self, cart_client, product):
        """Повторный POST того же товара → quantity += delta (не дубль)."""
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )
        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 3},
        )

        assert response.status_code == 201
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["quantity"] == 5
        assert body["total_items"] == 5

    @pytest.mark.asyncio
    async def test_add_nonexistent_product_404(self, cart_client):
        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": 999999, "quantity": 1},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_add_soft_deleted_product_404(
        self, cart_client, db_session, product
    ):
        """Soft-deleted товар нельзя добавить в корзину."""
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_validates_quantity_ge_1(self, cart_client, product):
        """quantity >= 1 — иначе 422."""
        response = await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 0},
        )
        assert response.status_code == 422


class TestGuestCartUpdate:
    """PATCH /cart/items/{product_id} — абсолютное количество."""

    @pytest.mark.asyncio
    async def test_patch_sets_absolute_quantity(self, cart_client, product):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )
        response = await cart_client.patch(
            f"/api/v1/cart/items/{product.id}",
            json={"quantity": 7},
        )

        assert response.status_code == 200
        assert response.json()["items"][0]["quantity"] == 7

    @pytest.mark.asyncio
    async def test_patch_zero_removes_item(self, cart_client, product):
        """quantity=0 → позиция удаляется."""
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )
        response = await cart_client.patch(
            f"/api/v1/cart/items/{product.id}",
            json={"quantity": 0},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total_items"] == 0

    @pytest.mark.asyncio
    async def test_patch_nonexistent_item_is_noop(self, cart_client, product):
        """
        PATCH несуществующей позиции для гостя — no-op, 200 с пустой корзиной.

        Для гостя это осознанное решение: корзина эфемерна, 404-логика
        добавила бы лишний edge case без пользы.
        """
        response = await cart_client.patch(
            f"/api/v1/cart/items/{product.id}",
            json={"quantity": 5},
        )

        assert response.status_code == 200
        assert response.json()["items"] == []


class TestGuestCartDelete:
    """DELETE /cart/items/{product_id} — удаление позиции."""

    @pytest.mark.asyncio
    async def test_delete_removes_item(self, cart_client, product):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
        )
        response = await cart_client.delete(f"/api/v1/cart/items/{product.id}")

        assert response.status_code == 200
        assert response.json()["items"] == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_idempotent(self, cart_client, product):
        """Удаление несуществующей позиции — 200, корзина пустая."""
        response = await cart_client.delete(f"/api/v1/cart/items/{product.id}")
        assert response.status_code == 200
        assert response.json()["items"] == []

    @pytest.mark.asyncio
    async def test_clear_cart(self, cart_client, product):
        """DELETE /cart — полностью очищает корзину (204)."""
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 3},
        )
        response = await cart_client.delete("/api/v1/cart")
        assert response.status_code == 204

        # Проверяем, что корзина пуста
        check = await cart_client.get("/api/v1/cart")
        assert check.json()["items"] == []


class TestGuestCartRead:
    """GET /cart — чтение корзины гостя."""

    @pytest.mark.asyncio
    async def test_get_empty_cart(self, cart_client):
        """Пустая корзина без ошибок."""
        response = await cart_client.get("/api/v1/cart")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total_items"] == 0
        assert body["hidden_items_count"] == 0

    @pytest.mark.asyncio
    async def test_get_reads_from_redis(self, cart_client, product):
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )
        response = await cart_client.get("/api/v1/cart")

        assert response.status_code == 200
        body = response.json()
        assert body["total_items"] == 2
        assert body["items"][0]["quantity"] == 2

    @pytest.mark.asyncio
    async def test_total_cost_uses_snapshot(
        self, cart_client, db_session, product
    ):
        """
        total_cost = snapshot_cost * quantity.

        Меняем цену товара после добавления в корзину — total_cost
        не меняется, потому что снимок зафиксирован.
        """
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 2},
        )
        original_cost = product.cost

        # Меняем цену товара
        product.cost = original_cost + Decimal("500.00")
        await db_session.flush()

        response = await cart_client.get("/api/v1/cart")
        body = response.json()

        expected_total = original_cost * 2
        assert Decimal(body["total_cost"]) == expected_total


class TestGuestCartSoftDeleted:
    """Фильтрация soft-deleted товаров и hidden_items_count."""

    @pytest.mark.asyncio
    async def test_soft_deleted_product_hidden(
        self, cart_client, db_session, product
    ):
        """Soft-deleted товар не показывается, но hidden_items_count растёт."""
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
        )

        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        response = await cart_client.get("/api/v1/cart")
        body = response.json()
        assert body["items"] == []
        assert body["hidden_items_count"] == 1

    @pytest.mark.asyncio
    async def test_mixed_cart_counts_hidden(
        self, cart_client, db_session, category, product
    ):
        """Один видимый + один удалённый → 1 в items, 1 в hidden_items_count."""
        from app.models.product import Product as ProductModel

        visible = ProductModel(
            name="Visible", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(visible)
        await db_session.flush()

        # Добавляем оба товара
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
        )
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": visible.id, "quantity": 1},
        )

        # Удаляем один
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        response = await cart_client.get("/api/v1/cart")
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["product_id"] == visible.id
        assert body["hidden_items_count"] == 1


class TestGuestCartSnapshot:
    """snapshot_cost vs current_cost."""

    @pytest.mark.asyncio
    async def test_snapshot_cost_does_not_change(
        self, cart_client, db_session, product
    ):
        """
        Снимок цены: изменение cost товара НЕ меняет snapshot_cost,
        но current_cost обновляется.
        """
        await cart_client.post(
            "/api/v1/cart/items",
            json={"product_id": product.id, "quantity": 1},
        )
        original_cost = product.cost

        product.cost = original_cost + Decimal("1000.00")
        await db_session.flush()

        response = await cart_client.get("/api/v1/cart")
        item = response.json()["items"][0]

        assert Decimal(item["snapshot_cost"]) == original_cost
        assert Decimal(item["current_cost"]) == original_cost + Decimal("1000.00")