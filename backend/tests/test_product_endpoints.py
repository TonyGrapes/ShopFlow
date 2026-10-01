"""
API-тесты эндпоинтов /api/v1/products.

Покрывают контракты:
- GET    /products                       — список с пагинацией
- GET    /products/{id}                  — детали, 404 для удалённых
- POST   /products                       — создание, 201
- PATCH  /products/{id}                  — частичное обновление
- DELETE /products/{id}                  — soft delete, 204
- POST   /products/{id}/images           — загрузка, 415 при плохом файле
- DELETE /products/{id}/images/{img_id}  — удаление изображения

Все тесты используют фикстуры из conftest:
- client       — HTTP-клиент с override get_db и get_storage
- db_session   — изолированная транзакция в тестовой БД
- category     — готовая категория (ltree)
- product      — готовый товар
- mock_storage — мок MinioStorage с AsyncMock-методами
"""
import io
from decimal import Decimal

import pytest
from app.models.product import Product
from sqlalchemy import select

# ============================================================
#  GET /api/v1/products — список
# ============================================================

class TestListProductsEndpoint:
    """Контракт GET /api/v1/products."""

    @pytest.mark.asyncio
    async def test_list_products_empty(self, client):
        """Пустая БД → пустой список."""
        response = await client.get("/api/v1/products")

        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_list_products_with_item(self, client, product):
        """Один товар в БД → попадает в список."""
        response = await client.get("/api/v1/products")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == product.id
        assert body["items"][0]["name"] == "Laptop"

    @pytest.mark.asyncio
    async def test_list_products_pagination(self, client, db_session, category):
        """Пагинация: page_size=2 → максимум 2 в items."""
        for i in range(5):
            db_session.add(
                Product(
                    name=f"Product {i}",
                    description="Test",
                    cost=Decimal("100.00"),
                    category_id=category.id,
                )
            )
        await db_session.flush()

        response = await client.get("/api/v1/products?page=1&page_size=2")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_products_rejects_bad_pagination(self, client):
        """page_size > 100 → 422."""
        response = await client.get("/api/v1/products?page_size=101")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_products_filters_deleted(self, client, db_session, product):
        """Удалённые товары не попадают в список."""
        from datetime import datetime, timezone

        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        response = await client.get("/api/v1/products")
        assert response.status_code == 200
        assert response.json()["total"] == 0


# ============================================================
#  GET /api/v1/products/{id}
# ============================================================

class TestGetProductEndpoint:
    """Контракт GET /api/v1/products/{id}."""

    @pytest.mark.asyncio
    async def test_get_product_success(self, client, product: Product):
        """Успешный GET."""
        response = await client.get(f"/api/v1/products/{product.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == product.id
        assert body["name"] == "Laptop"
        assert body["cost"] == "1000.00"

    @pytest.mark.asyncio
    async def test_get_product_404_correct_message(self, client):
        """404 возвращает 'Product not found'."""
        response = await client.get("/api/v1/products/999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Product not found"

    @pytest.mark.asyncio
    async def test_get_deleted_product_returns_404(
        self, client, db_session, product: Product
    ):
        """Удалённый товар недоступен."""
        from datetime import datetime, timezone

        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        response = await client.get(f"/api/v1/products/{product.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_product_includes_category(self, client, product):
        """В ответе есть вложенная категория."""
        response = await client.get(f"/api/v1/products/{product.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["category"] is not None
        assert body["category"]["category_name"] == "Electronics"

    @pytest.mark.asyncio
    async def test_get_product_images_empty_list(self, client, product):
        """Если изображений нет, отдаётся []."""
        response = await client.get(f"/api/v1/products/{product.id}")

        assert response.status_code == 200
        assert response.json()["images"] == []


# ============================================================
#  POST /api/v1/products — создание
# ============================================================

class TestCreateProductEndpoint:
    """Контракт POST /api/v1/products."""

    @pytest.mark.asyncio
    async def test_create_product_success(self, client, category, admin_headers):
        """Успешное создание → 201."""
        payload = {
            "name": "Smartphone",
            "description": "Flagship phone",
            "cost": "999.99",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Smartphone"
        assert body["cost"] == "999.99"
        assert body["category"] is not None
        assert body["category"]["id"] == category.id
        assert body["images"] == []

    @pytest.mark.asyncio
    async def test_create_product_without_description_returns_422(
        self, client, category, admin_headers
    ):
        payload = {
            "name": "Smartphone",
            "cost": "999.99",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(e["loc"] == ["body", "description"] for e in errors)

    @pytest.mark.asyncio
    async def test_create_product_without_cost_returns_422(
        self, client, category, admin_headers
    ):
        payload = {
            "name": "Smartphone",
            "description": "Flagship",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_product_invalid_category_returns_422(
        self, client, admin_headers
    ):
        payload = {
            "name": "Ghost",
            "description": "Test",
            "cost": "100.00",
            "category_id": 999999,
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422
        assert "999999" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_product_rejects_extra_fields(
        self, client, category, admin_headers
    ):
        payload = {
            "name": "Smartphone",
            "description": "Flagship",
            "cost": "999.99",
            "category_id": category.id,
            "hacker_field": "hacked",
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_product_short_name_returns_422(
        self, client, category, admin_headers
    ):
        payload = {
            "name": "AB",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422

# ============================================================
#  PATCH /api/v1/products/{id} — частичное обновление
# ============================================================

class TestUpdateProductEndpoint:
    """Контракт PATCH /api/v1/products/{id}."""

    @pytest.mark.asyncio
    async def test_patch_product_success(
        self, client, product, admin_headers
    ):
        response = await client.patch(
            f"/api/v1/products/{product.id}",
            json={"name": "Updated Laptop"},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Updated Laptop"
        assert body["cost"] == "1000.00"

    @pytest.mark.asyncio
    async def test_patch_product_partial_update(
        self, client, product, admin_headers
    ):
        response = await client.patch(
            f"/api/v1/products/{product.id}",
            json={"cost": "555.55"},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 200
        assert response.json()["cost"] == "555.55"

    @pytest.mark.asyncio
    async def test_patch_missing_returns_404(self, client, admin_headers):
        response = await client.patch(
            "/api/v1/products/999999",
            json={"name": "Updated Name"},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_short_name_returns_422(
        self, client, product, admin_headers
    ):
        response = await client.patch(
            f"/api/v1/products/{product.id}",
            json={"name": "X"},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_invalid_category_returns_422(
        self, client, product, admin_headers
    ):
        response = await client.patch(
            f"/api/v1/products/{product.id}",
            json={"category_id": 999999},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 422
        assert "999999" in response.json()["detail"]

# ============================================================
#  DELETE /api/v1/products/{id} — soft delete
# ============================================================

class TestDeleteProductEndpoint:
    """Контракт DELETE /api/v1/products/{id}."""

    @pytest.mark.asyncio
    async def test_delete_product_returns_204(
        self, client, product, admin_headers
    ):
        response = await client.delete(
            f"/api/v1/products/{product.id}",
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_soft_marks_deleted_at(
        self, client, db_session, product, admin_headers
    ):
        await client.delete(
            f"/api/v1/products/{product.id}",
            headers=admin_headers,           # ← добавить
        )
        result = await db_session.execute(
            select(Product).where(Product.id == product.id)
        )
        fresh = result.scalar_one()
        assert fresh.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_twice_returns_404(
        self, client, product, admin_headers
    ):
        first = await client.delete(
            f"/api/v1/products/{product.id}",
            headers=admin_headers,           # ← добавить
        )
        assert first.status_code == 204

        second = await client.delete(
            f"/api/v1/products/{product.id}",
            headers=admin_headers,           # ← добавить
        )
        assert second.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_missing_returns_404(self, client, admin_headers):
        response = await client.delete(
            "/api/v1/products/999999",
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 404

# ============================================================
#  POST /api/v1/products/{id}/images — загрузка
# ============================================================

class TestUploadImageEndpoint:
    """Контракт POST /api/v1/products/{id}/images."""

    @pytest.mark.asyncio
    async def test_upload_valid_image(
        self, client, product, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        file_content = b"fake-jpeg-content"
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("photo.jpg", file_content, "image/jpeg")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 200
        mock_storage.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_rejects_bad_extension(
        self, client, product, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("malware.exe", b"data", "application/octet-stream")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 415
        assert "not allowed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_rejects_bad_content_type(
        self, client, product, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="text/plain",
        )
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("file.txt", b"data", "text/plain")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_upload_to_missing_product(
        self, client, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        response = await client.post(
            "/api/v1/products/999999/images",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_fails_at_minio_no_compensation(
        self, client, product, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        mock_storage.upload.side_effect = Exception("S3 down")
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 500
        mock_storage.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_compensates_when_db_fails(
        self, client, product, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        mocker.patch(
            "app.api.v1.endpoints.products.ProductImage",
            side_effect=Exception("DB constraint"),
        )
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 500
        mock_storage.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_key_has_product_prefix(
        self, client, product, mock_storage, mocker, admin_headers
    ):
        mocker.patch(
            "app.api.v1.endpoints.products.magic.from_buffer",
            return_value="image/jpeg",
        )
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 200
        call_kwargs = mock_storage.upload.await_args.kwargs
        assert call_kwargs["key"].startswith(f"products/{product.id}/")

# ============================================================
#  DELETE /api/v1/products/{id}/images/{image_id} — удаление
# ============================================================

class TestDeleteImageEndpoint:
    """Контракт DELETE /api/v1/products/{id}/images/{image_id}."""

    @pytest.mark.asyncio
    async def test_delete_image_missing_returns_404(
        self, client, product, mock_storage, admin_headers
    ):
        response = await client.delete(
            f"/api/v1/products/{product.id}/images/999999",
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_image_of_missing_product_returns_404(
        self, client, mock_storage, admin_headers
    ):
        response = await client.delete(
            "/api/v1/products/999999/images/1",
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 404

    # ✅ Happy path — если его добавляли
    @pytest.mark.asyncio
    async def test_delete_image_happy_path(
        self, client, db_session, product, mock_storage, admin_headers
    ):
        from app.models.product import ProductImage
        image = ProductImage(
            product_id=product.id,
            key=f"products/{product.id}/test.png",
        )
        db_session.add(image)
        await db_session.flush()
        await db_session.refresh(image)

        response = await client.delete(
            f"/api/v1/products/{product.id}/images/{image.id}",
            headers=admin_headers,           # ← добавить
        )
        assert response.status_code == 204

        # Строка удалена
        result = await db_session.execute(
            select(ProductImage).where(ProductImage.id == image.id)
        )
        assert result.scalar_one_or_none() is None

        # storage.delete вызван с key
        mock_storage.delete.assert_awaited_once_with(key=image.key)

class TestListProductsFilters:
    """API-тесты фильтров."""

    @pytest.mark.asyncio
    async def test_min_cost_filter(self, client, db_session, category):
        from decimal import Decimal
        for i, cost in enumerate([Decimal("10"), Decimal("100"), Decimal("500")]):
            db_session.add(Product(
                name=f"P{i}", description="Test",
                cost=cost, category_id=category.id,
            ))
        await db_session.flush()

        response = await client.get("/api/v1/products?min_cost=50")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_sort_by_cost_desc(self, client, db_session, category):
        from decimal import Decimal
        for i, cost in enumerate([Decimal("100"), Decimal("500"), Decimal("50")]):
            db_session.add(Product(
                name=f"P{i}", description="Test",
                cost=cost, category_id=category.id,
            ))
        await db_session.flush()

        response = await client.get("/api/v1/products?sort_by=cost&sort_order=desc")
        body = response.json()

        costs = [Decimal(item["cost"]) for item in body["items"]]
        assert costs == sorted(costs, reverse=True)

    @pytest.mark.asyncio
    async def test_invalid_sort_by_returns_422(self, client):
        """sort_by вне белого списка → 422."""
        response = await client.get("/api/v1/products?sort_by=hack")
        assert response.status_code == 422


class TestAuthOnWriteEndpoints:
    """Поведенческая проверка: write требует токен, read — нет."""

    @pytest.mark.asyncio
    async def test_post_without_token_returns_401(
        self, client, category
    ):
        """POST без Authorization → 401."""
        payload = {
            "name": "No Auth Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post("/api/v1/products", json=payload)

        assert response.status_code == 401
        assert "Authorization" in response.json()["detail"]
        # Проверяем заголовок по стандарту
        assert response.headers.get("WWW-Authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_post_with_token_returns_201(
        self, client, category, admin_headers
    ):
        """POST с валидным admin-токеном → 201."""
        payload = {
            "name": "Auth Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products",
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Auth Product"

    @pytest.mark.asyncio
    async def test_patch_without_token_returns_401(self, client, product):
        """PATCH без токена → 401."""
        response = await client.patch(
            f"/api/v1/products/{product.id}",
            json={"name": "Hacked Name"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_without_token_returns_401(self, client, product):
        """DELETE без токена → 401."""
        response = await client.delete(f"/api/v1/products/{product.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_without_token_returns_401(
        self, client, product, mock_storage
    ):
        """POST /images без токена → 401 (не вызывает storage)."""
        response = await client.post(
            f"/api/v1/products/{product.id}/images",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )
        assert response.status_code == 401
        mock_storage.upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_products_public_no_token(self, client):
        """GET /products доступен без токена (публичный)."""
        response = await client.get("/api/v1/products")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_product_by_id_public(self, client, product):
        """GET /products/{id} доступен без токена."""
        response = await client.get(f"/api/v1/products/{product.id}")
        assert response.status_code == 200

class TestCreateProductDuplicateName:
    """409 при дубликате активного имени."""

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_409(
        self, client, category, admin_headers
    ):
        payload = {
            "name": "Unique Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        first = await client.post(
            "/api/v1/products", json=payload, headers=admin_headers
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/v1/products", json=payload, headers=admin_headers
        )
        assert second.status_code == 409
        assert "Unique Product" in second.json()["detail"]

    @pytest.mark.asyncio
    async def test_duplicate_after_soft_delete_allowed(
        self, client, db_session, category, admin_headers
    ):
        """Soft-deleted товар освобождает имя (partial index)."""
        from datetime import datetime, timezone

        from app.models.product import Product

        # Создаём первый товар
        payload = {
            "name": "Reusable Name",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        first = await client.post(
            "/api/v1/products", json=payload, headers=admin_headers
        )
        pid = first.json()["id"]

        # Soft delete
        product = await db_session.get(Product, pid)
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        # Повторное создание с тем же именем — должно пройти
        second = await client.post(
            "/api/v1/products", json=payload, headers=admin_headers
        )
        assert second.status_code == 201

class TestNoNPlusOne:
    """Доказательство отсутствия N+1 на GET /products."""

    @pytest.mark.asyncio
    async def test_list_products_uses_constant_number_of_queries(
        self, client, db_session, category, sql_counter
    ):
        """
        ✅ 4 запроса: count + items + categories IN + product_images IN.
        Независимо от количества товаров.
        """
        from decimal import Decimal

        from app.models.product import Product, ProductImage

        # 3 товара, у каждого 2 картинки
        for i in range(3):
            product = Product(
                name=f"Product {i}",
                description="Test",
                cost=Decimal("100.00"),
                category_id=category.id,
            )
            db_session.add(product)
            await db_session.flush()

            for j in range(2):
                db_session.add(ProductImage(
                    product_id=product.id,
                    key=f"products/{product.id}/img{j}.png",
                ))
        await db_session.flush()

        # Сбрасываем счётчик — фикстуры тоже делали запросы
        sql_counter.statements.clear()

        response = await client.get("/api/v1/products")
        assert response.status_code == 200
        assert response.json()["total"] == 3

        # ✅ Ожидаем ровно 4 SELECT-запроса
        # 1. COUNT для total
        # 2. SELECT products с LIMIT/OFFSET
        # 3. SELECT categories WHERE id IN (...)
        # 4. SELECT product_images WHERE product_id IN (...)
        selects = [s for s in sql_counter.statements if s.strip().upper().startswith("SELECT")]
        assert len(selects) == 4, (
            f"Expected 4 SELECTs, got {len(selects)}:\n" + "\n---\n".join(selects)
        )