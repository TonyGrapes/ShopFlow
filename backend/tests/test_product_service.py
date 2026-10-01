# tests/test_product_service.py
from decimal import Decimal

import pytest
from app.db.enum import ProductStatus
from app.models.product import Product, ProductImage
from app.schemas.product import ProductCreate
from app.services import product_service
from app.services.product_service import (
    serialize_product,
    serialize_product_list_item,
)
from fastapi import HTTPException
from pydantic import ValidationError


def money(value: str = "100.00") -> Decimal:
    """Хелпер для Money-значений в тестах"""
    return Decimal(value)


class TestCreateProduct:

    @pytest.mark.asyncio
    async def test_create_product_success(self, db_session, category):
        """ТЕСТ: успешное создание товара"""
        data = ProductCreate(
            name="Smartphone X",
            description="Flagship phone",
            cost=money("999.99"),
            category_id=category.id,
        )
        product = await product_service.create_product(db_session, data)

        assert product.id is not None
        assert product.name == "Smartphone X"
        assert product.cost == Decimal("999.99")
        assert product.category_id == category.id

    @pytest.mark.asyncio
    async def test_create_product_loads_relations(self, db_session, category):
        """
        ТЕСТ: create_product возвращает товар со связями.
        ДОКАЗЫВАЕТ Находку #6 — нет MissingGreenlet при сериализации.
        """
        data = ProductCreate(
            name="Smartphone X",
            description="Flagship",
            cost=money(),
            category_id=category.id,
        )
        product = await product_service.create_product(db_session, data)

        # Обращение к связям без запроса — они уже загружены
        assert product.category is not None
        assert product.category.id == category.id
        assert product.images == []

    @pytest.mark.asyncio
    async def test_create_product_with_invalid_category(self, db_session):
        """
        ТЕСТ: несуществующая категория → 422.
        ДОКАЗЫВАЕТ Находку #8 — 422 вместо 500.
        """
        data = ProductCreate(
            name="Bad Product",
            description="Test",
            cost=money(),
            category_id=999999,
        )
        with pytest.raises(HTTPException) as exc_info:
            await product_service.create_product(db_session, data)

        assert exc_info.value.status_code == 422
        assert "999999" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_product_with_zero_cost(self, db_session, category):
        """
        ТЕСТ: cost=0 допустим (Money ge=0).
        ДОКАЗЫВАЕТ границы Money.
        """
        data = ProductCreate(
            name="Free Sample",
            description="Free sample product", 
            cost=Decimal("0.00"),
            category_id=category.id,
        )
        product = await product_service.create_product(db_session, data)
        assert product.cost == Decimal("0.00")

    def test_create_product_schema_rejects_negative_cost(self):
        """ТЕСТ: cost < 0 → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(
                name="Bad",
                cost=Decimal("-1.00"),
                category_id=1,
            )
        assert any(e["loc"] == ("cost",) for e in exc_info.value.errors())

    def test_create_product_schema_rejects_cost_with_three_decimals(self):
        """ТЕСТ: cost с 3 знаками после запятой → ValidationError"""
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Bad",
                cost=Decimal("100.123"),  # decimal_places=2
                category_id=1,
            )

    def test_create_product_schema_rejects_cost_too_large(self):
        """ТЕСТ: cost > 10 знаков → ValidationError"""
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Bad",
                cost=Decimal("12345678901"),  # 11 знаков
                category_id=1,
            )

    def test_create_product_schema_requires_cost(self):
        """ТЕСТ: без cost → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(name="Test", category_id=1)
        assert any(e["loc"] == ("cost",) for e in exc_info.value.errors())

    def test_create_product_schema_requires_category(self):
        """ТЕСТ: без category_id → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(name="Test", cost=money())
        assert any(e["loc"] == ("category_id",) for e in exc_info.value.errors())

    def test_create_product_schema_rejects_zero_category(self):
        """ТЕСТ: category_id=0 запрещён (gt=0)"""
        with pytest.raises(ValidationError):
            ProductCreate(name="Test", cost=money(), category_id=0)

    def test_create_product_schema_rejects_short_name(self):
        """ТЕСТ: name короче 3 символов → ValidationError"""
        with pytest.raises(ValidationError):
            ProductCreate(name="AB", cost=money(), category_id=1)

    def test_create_product_schema_rejects_extra_fields(self):
        """ТЕСТ: extra="forbid" запрещает лишние поля"""
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Test Product",
                cost=money(),
                category_id=1,
                unknown="hack",
            )
    def test_create_product_schema_requires_description(self):
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(
                name="Test",
                cost=Decimal("100.00"),
                category_id=1,
                # description НЕ передан
            )
        assert any(e["loc"] == ("description",) for e in exc_info.value.errors())


    """Дополнительные тесты product_service: сериализация и фильтры."""



class TestSerializeProduct:
    """Тесты сериализации с публичными URL."""

    @pytest.mark.asyncio
    async def test_serialize_product_includes_image_urls(
        self, db_session, category, mocker
    ):
        """✅ images[].url формируется из key через storage.get_url."""
        product = Product(
            name="Test", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(product)
        await db_session.flush()

        image = ProductImage(product_id=product.id, key="products/1/abc.jpg")
        db_session.add(image)
        await db_session.flush()
        await db_session.refresh(product, ["images"])

        mock_storage = mocker.Mock()
        mock_storage.get_url = mocker.Mock(
            return_value="http://cdn.test/shopflow-media/products/1/abc.jpg"
        )
        mocker.patch(
            "app.services.product_service.get_storage",
            return_value=mock_storage,
        )

        result = serialize_product(product)

        # ✅ Pydantic-объект, а не dict
        assert result.images[0].url == "http://cdn.test/shopflow-media/products/1/abc.jpg"
        mock_storage.get_url.assert_called_once_with("products/1/abc.jpg")


class TestSerializeProductListItem:
    """Тесты cover_url."""

    @pytest.mark.asyncio
    async def test_serialize_list_item_with_cover(
        self, db_session, category, mocker
    ):
        """✅ cover_url заполняется, если есть картинки."""
        product = Product(
            name="Test", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(product)
        await db_session.flush()

        db_session.add(ProductImage(product_id=product.id, key="products/1/cover.jpg"))
        await db_session.flush()
        await db_session.refresh(product, ["images"])

        mock_storage = mocker.Mock()
        mock_storage.get_url = mocker.Mock(return_value="http://cdn.test/cover.jpg")
        mocker.patch(
            "app.services.product_service.get_storage",
            return_value=mock_storage,
        )

        result = serialize_product_list_item(product)

        # ✅ Pydantic-объект
        assert result.cover_url == "http://cdn.test/cover.jpg"

    @pytest.mark.asyncio
    async def test_serialize_list_item_without_cover(
        self, db_session, category
    ):
        """cover_url = None, если картинок нет."""
        product = Product(
            name="Test", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(product)
        await db_session.flush()
        await db_session.refresh(product, ["images"])

        result = serialize_product_list_item(product)

        assert result.cover_url is None
        

class TestListProductsFilters:
    """Тесты фильтров и сортировок."""

    @pytest.mark.asyncio
    async def test_filter_by_min_cost(self, db_session, category):
        """✅ min_cost фильтрует."""
        for i, cost in enumerate([Decimal("10"), Decimal("100"), Decimal("500")]):
            db_session.add(Product(
                name=f"P{i}", description="Test",
                cost=cost, category_id=category.id,
            ))
        await db_session.flush()

        items, total = await product_service.list_products(
            db_session, min_cost=Decimal("50")
        )

        assert total == 2
        assert all(p.cost >= Decimal("50") for p in items)

    @pytest.mark.asyncio
    async def test_filter_by_max_cost(self, db_session, category):
        """✅ max_cost фильтрует."""
        for i, cost in enumerate([Decimal("10"), Decimal("100"), Decimal("500")]):
            db_session.add(Product(
                name=f"P{i}", description="Test",
                cost=cost, category_id=category.id,
            ))
        await db_session.flush()

        items, total = await product_service.list_products(
            db_session, max_cost=Decimal("200")
        )

        assert total == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db_session, category):
        """✅ status фильтрует."""
        db_session.add(Product(
            name="A", description="Test",
            cost=Decimal("100"), category_id=category.id,
            status=ProductStatus.AVAILABLE,
        ))
        db_session.add(Product(
            name="B", description="Test",
            cost=Decimal("100"), category_id=category.id,
            status=ProductStatus.DISCONTINUED,
        ))
        await db_session.flush()

        items, total = await product_service.list_products(
            db_session, status=ProductStatus.AVAILABLE
        )

        assert total == 1
        assert items[0].name == "A"

    @pytest.mark.asyncio
    async def test_sort_by_cost_desc(self, db_session, category):
        """✅ sort_by=cost, sort_order=desc."""
        for i, cost in enumerate([Decimal("100"), Decimal("500"), Decimal("50")]):
            db_session.add(Product(
                name=f"P{i}", description="Test",
                cost=cost, category_id=category.id,
            ))
        await db_session.flush()

        items, _ = await product_service.list_products(
            db_session, sort_by="cost", sort_order="desc"
        )

        costs = [p.cost for p in items]
        assert costs == sorted(costs, reverse=True)