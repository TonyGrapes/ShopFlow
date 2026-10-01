# tests/test_product_cache.py
"""
Тесты кэша каталога: hit/miss, инвалидация, независимость ключей, X-Cache.
"""
from decimal import Decimal

import pytest

from app.models.product import Product


class TestXCacheHeader:
    """Заголовок X-Cache: HIT/MISS — инструмент доказательств."""

    @pytest.mark.asyncio
    async def test_first_request_miss(self, client, mock_cache, product):
        """Первый запрос → MISS."""
        mock_cache._storage.clear()

        response = await client.get("/api/v1/products")

        assert response.status_code == 200
        assert response.headers["X-Cache"] == "MISS"

    @pytest.mark.asyncio
    async def test_second_request_hit(self, client, mock_cache, product):
        """Второй запрос → HIT."""
        mock_cache._storage.clear()

        first = await client.get("/api/v1/products")
        assert first.headers["X-Cache"] == "MISS"

        second = await client.get("/api/v1/products")
        assert second.headers["X-Cache"] == "HIT"

    @pytest.mark.asyncio
    async def test_different_filters_different_cache_entries(
        self, client, mock_cache, product
    ):
        """Разные фильтры → разные ключи → оба MISS."""
        mock_cache._storage.clear()

        r1 = await client.get("/api/v1/products?min_cost=50")
        r2 = await client.get("/api/v1/products?max_cost=500")

        assert r1.headers["X-Cache"] == "MISS"
        assert r2.headers["X-Cache"] == "MISS"       # другой ключ

        # Второй раз оба HIT
        r3 = await client.get("/api/v1/products?min_cost=50")
        r4 = await client.get("/api/v1/products?max_cost=500")

        assert r3.headers["X-Cache"] == "HIT"
        assert r4.headers["X-Cache"] == "HIT"


class TestCacheInvalidation:
    """Инвалидация при мутациях."""

    @pytest.mark.asyncio
    async def test_create_invalidates_cache(
        self, client, mock_cache, category, admin_headers    # ← client вместо client
    ):
        """POST → все ключи products:list:* удалены."""
        mock_cache._storage.clear()
        await client.get("/api/v1/products")
        assert len(mock_cache._storage) >= 1

        payload = {
            "name": "New Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products", json=payload, headers=admin_headers
        )
        assert response.status_code == 201

        assert len(mock_cache._storage) == 0

    @pytest.mark.asyncio
    async def test_patch_invalidates_cache(
        self, client, mock_cache, product, admin_headers      # ← client
    ):
        mock_cache._storage.clear()
        await client.get("/api/v1/products")
        assert len(mock_cache._storage) >= 1

        response = await client.patch(
            f"/api/v1/products/{product.id}",
            json={"name": "Updated"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert len(mock_cache._storage) == 0

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(
        self, client, mock_cache, product, admin_headers      # ← client
    ):
        mock_cache._storage.clear()
        await client.get("/api/v1/products")
        assert len(mock_cache._storage) >= 1

        response = await client.delete(
            f"/api/v1/products/{product.id}", headers=admin_headers
        )
        assert response.status_code == 204
        assert len(mock_cache._storage) == 0

    @pytest.mark.asyncio
    async def test_upload_image_invalidates_cache(
        self, client, mock_cache, product, mock_storage,
        mocker, admin_headers                                 # ← client
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        mock_cache._storage.clear()
        await client.get("/api/v1/products")
        assert len(mock_cache._storage) >= 1

        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert len(mock_cache._storage) == 0

class TestCacheKeyIsolation:
    """Независимость ключей по параметрам."""

    @pytest.mark.asyncio
    async def test_page_isolation(self, client, mock_cache, product):
        """page=1 и page=2 — разные ключи."""
        mock_cache._storage.clear()

        await client.get("/api/v1/products?page=1")
        await client.get("/api/v1/products?page=2")

        assert len(mock_cache._storage) == 2

    @pytest.mark.asyncio
    async def test_sort_isolation(self, client, mock_cache, product):
        """Разные sort_by — разные ключи."""
        mock_cache._storage.clear()

        await client.get("/api/v1/products?sort_by=id")
        await client.get("/api/v1/products?sort_by=cost")

        assert len(mock_cache._storage) == 2

    @pytest.mark.asyncio
    async def test_all_filters_in_key(self, client, mock_cache, product):
        """Все фильтры входят в ключ."""
        mock_cache._storage.clear()

        urls = [
            "/api/v1/products",
            "/api/v1/products?page=2",
            "/api/v1/products?page_size=10",
            "/api/v1/products?min_cost=50",
            "/api/v1/products?max_cost=500",
            "/api/v1/products?sort_by=cost",
            "/api/v1/products?sort_order=desc",
        ]

        for url in urls:
            await client.get(url)

        assert len(mock_cache._storage) == len(urls)