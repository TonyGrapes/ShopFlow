"""
Тесты Pydantic-схем продукта.

Покрывают контракты:
- ProductCreate: обязательные поля (name, description, cost, category_id),
  ограничения (ge, max_digits, decimal_places, min_length, extra="forbid")
- ProductUpdate: PATCH-семантика (все поля Optional, exclude_unset)
- ProductResponse: сериализация из ORM-объекта, вложенные связи
- ProductListItem: lightweight для списка

Синхронизированы с последними изменениями:
- description: str (обязательное) — соответствует NOT NULL в модели
- ProductImageBrief.url — через validation_alias="image_url"
- cover_url — @property в модели Product
"""
import types
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.db.enum import ProductStatus
from app.schemas.product import (
    CategoryBrief,
    ProductCreate,
    ProductImageBrief,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)

# ===================== Вспомогательные фикстуры =====================

VALID_NAME = "Gaming Laptop"
VALID_DESCRIPTION = "High-end gaming laptop"
VALID_COST = Decimal("1999.99")
VALID_CATEGORY_ID = 1


def make_create_payload(**overrides):
    """Базовый валидный payload для ProductCreate с возможностью переопределения."""
    base = {
        "name": VALID_NAME,
        "description": VALID_DESCRIPTION,
        "cost": VALID_COST,
        "category_id": VALID_CATEGORY_ID,
    }
    base.update(overrides)
    return base


# ===================== ProductCreate =====================

class TestProductCreate:
    """Контракт схемы ProductCreate."""

    # ---------- Happy path ----------

    def test_create_valid_data_passes(self):
        """Успешное создание со всеми обязательными полями."""
        schema = ProductCreate(**make_create_payload())

        assert schema.name == VALID_NAME
        assert schema.description == VALID_DESCRIPTION
        assert schema.cost == VALID_COST
        assert schema.category_id == VALID_CATEGORY_ID
        assert schema.status == ProductStatus.AVAILABLE  # default

    def test_create_accepts_zero_cost(self):
        """Money ge=0 — ноль допустим."""
        schema = ProductCreate(**make_create_payload(cost=Decimal("0.00")))
        assert schema.cost == Decimal("0.00")

    def test_create_accepts_exactly_two_decimals(self):
        """decimal_places=2 — два знака после запятой — ок."""
        schema = ProductCreate(**make_create_payload(cost=Decimal("10.99")))
        assert schema.cost == Decimal("10.99")

    def test_create_accepts_max_length_name(self):
        """max_length=255 — граница проходит."""
        name = "A" * 255
        schema = ProductCreate(**make_create_payload(name=name))
        assert len(schema.name) == 255

    def test_create_accepts_status_override(self):
        """status можно переопределить."""
        schema = ProductCreate(**make_create_payload(status=ProductStatus.OUTOFSTOCK))
        assert schema.status == ProductStatus.OUTOFSTOCK

    # ---------- Обязательные поля ----------

    def test_create_rejects_missing_name(self):
        """Без name → ValidationError на ('name',)."""
        payload = make_create_payload()
        del payload["name"]

        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**payload)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_create_rejects_missing_description(self):
        """
        Без description → ValidationError.

        ДОКАЗЫВАЕТ: схема согласована с моделью (description NOT NULL).
        """
        payload = make_create_payload()
        del payload["description"]

        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**payload)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("description",) for e in errors)

    def test_create_rejects_missing_cost(self):
        """Без cost → ValidationError на ('cost',)."""
        payload = make_create_payload()
        del payload["cost"]

        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**payload)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("cost",) for e in errors)

    def test_create_rejects_missing_category_id(self):
        """Без category_id → ValidationError на ('category_id',)."""
        payload = make_create_payload()
        del payload["category_id"]

        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**payload)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("category_id",) for e in errors)

    # ---------- Валидация cost ----------

    def test_create_rejects_negative_cost(self):
        """Money ge=0 — отрицательный cost запрещён."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(cost=Decimal("-1")))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("cost",) for e in errors)

    def test_create_rejects_too_many_decimals(self):
        """decimal_places=2 — 4 знака после запятой запрещены."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(cost=Decimal("10.9999")))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("cost",) for e in errors)

    def test_create_rejects_cost_with_too_many_digits(self):
        """max_digits=10 — 11+ знаков до запятой запрещены."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(cost=Decimal("12345678901")))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("cost",) for e in errors)

    # ---------- Валидация name ----------

    def test_create_rejects_short_name(self):
        """min_length=3 — имя короче 3 символов запрещено."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(name="La"))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_create_rejects_too_long_name(self):
        """max_length=255 — 256+ символов запрещено."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(name="A" * 256))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    # ---------- Валидация description ----------

    def test_create_rejects_empty_description(self):
        """
        description min_length=1 — пустая строка запрещена.

        ДОКАЗЫВАЕТ: схема жёстче, чем просто NOT NULL.
        """
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(description=""))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("description",) for e in errors)

    def test_create_rejects_too_long_description(self):
        """description max_length=5000."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(description="A" * 5001))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("description",) for e in errors)

    # ---------- Валидация category_id ----------

    def test_create_rejects_zero_category_id(self):
        """gt=0 — нулевой category_id запрещён."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(category_id=0))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("category_id",) for e in errors)

    def test_create_rejects_negative_category_id(self):
        """gt=0 — отрицательный category_id запрещён."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**make_create_payload(category_id=-1))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("category_id",) for e in errors)

    # ---------- extra="forbid" ----------

    def test_create_rejects_extra_fields(self):
        """extra="forbid" — лишнее поле отклонено."""
        payload = make_create_payload()
        payload["hacker_field"] = "hacked"

        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(**payload)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("hacker_field",) for e in errors)


# ===================== ProductUpdate =====================

class TestProductUpdate:
    """Контракт схемы ProductUpdate — PATCH-семантика."""

    def test_update_empty_is_valid(self):
        """Пустой ProductUpdate валиден и даёт пустой dict."""
        update = ProductUpdate()
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_update_dump_excludes_unset(self):
        """Явно переданные None попадают в dump, отсутствующие — нет."""
        update = ProductUpdate(
            name=None,
            description=None,
            cost=None,
            status=None,
            category_id=None,
        )
        dumped = update.model_dump(exclude_unset=True)

        assert dumped["name"] is None
        assert dumped["description"] is None
        assert dumped["cost"] is None
        assert dumped["status"] is None
        assert dumped["category_id"] is None

    def test_update_only_sent_fields_in_dump(self):
        """Только переданные поля в dump."""
        update = ProductUpdate(cost=Decimal("199.99"))
        dumped = update.model_dump(exclude_unset=True)

        assert "cost" in dumped
        assert "name" not in dumped
        assert "description" not in dumped

    def test_update_distinguishes_null_from_absent(self):
        """
        description=None передан явно — попадает в dump.
        description НЕ передан — не попадает.
        """
        # Явно передан None
        update_with_null = ProductUpdate(description=None)
        dumped_with_null = update_with_null.model_dump(exclude_unset=True)
        assert dumped_with_null["description"] is None

        # Не передан вообще
        update_empty = ProductUpdate()
        dumped_empty = update_empty.model_dump(exclude_unset=True)
        assert "description" not in dumped_empty

    def test_update_rejects_negative_cost(self):
        """cost ge=0 — отрицательный запрещён."""
        with pytest.raises(ValidationError) as exc_info:
            ProductUpdate(cost=Decimal("-5"))

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("cost",) for e in errors)

    def test_update_rejects_zero_category_id(self):
        """category_id gt=0 — ноль запрещён."""
        with pytest.raises(ValidationError) as exc_info:
            ProductUpdate(category_id=0)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("category_id",) for e in errors)

    def test_update_rejects_short_name(self):
        """name min_length=3 — если передан, должен быть валидным."""
        with pytest.raises(ValidationError) as exc_info:
            ProductUpdate(name="Ab")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_update_allows_partial(self):
        """Можно обновить только name."""
        update = ProductUpdate(name="Updated Name")
        dumped = update.model_dump(exclude_unset=True)

        assert dumped == {"name": "Updated Name"}


# ===================== ProductResponse =====================

class TestProductResponse:
    """Контракт схемы ProductResponse — сериализация из ORM."""

    def test_response_from_orm_like_object(self):
        """Валидация из объекта с атрибутами (как ORM)."""
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            description="High-end laptop",
            cost=Decimal("1999.99"),
            category_id=1,
            category=None,
            images=[],
            status="available",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=None,
        )

        response = ProductResponse.model_validate(fake)

        assert response.id == 1
        assert response.name == "Laptop"
        assert response.description == "High-end laptop"
        assert response.cost == Decimal("1999.99")
        assert response.category is None
        assert response.images == []

    def test_response_from_includes_nested_category(self):
        """
        Вложенная CategoryBrief создаётся из dict.

        ДОКАЗЫВАЕТ: вложенная модель валидируется корректно.
        """
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            description="High-end",
            cost=Decimal("1999.99"),
            category_id=1,
            category={"id": 10, "category_name": "Electronics"},
            images=[],
            status="available",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=None,
        )

        response = ProductResponse.model_validate(fake)

        assert isinstance(response.category, CategoryBrief)
        assert response.category.id == 10
        assert response.category.category_name == "Electronics"

    def test_response_from_includes_nested_images(self):
        """Вложенные ProductImageBrief создаются из dict."""
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            description="High-end",
            cost=Decimal("1999.99"),
            category_id=1,
            category=None,
            images=[
                types.SimpleNamespace(id=100, url="https://cdn/img1.jpg"),
                types.SimpleNamespace(id=101, url="https://cdn/img2.jpg"),
            ],
            status="available",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=None,
        )

        response = ProductResponse.model_validate(fake)

        assert len(response.images) == 2
        assert response.images[0].url == "https://cdn/img1.jpg"
        assert response.images[1].url == "https://cdn/img2.jpg"

    def test_response_serializes_to_dict(self):
        """model_dump даёт плоский dict с корректными ключами."""
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            description="High-end",
            cost=Decimal("1999.99"),
            category_id=1,
            category=None,
            images=[],
            status="available",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=None,
        )

        response = ProductResponse.model_validate(fake)
        dumped = response.model_dump()

        assert dumped["id"] == 1
        assert dumped["name"] == "Laptop"
        assert dumped["description"] == "High-end"
        assert dumped["cost"] == Decimal("1999.99")


# ===================== ProductListItem =====================

class TestProductListItem:
    """Контракт схемы ProductListItem — облегчённая версия для списка."""

    def test_list_item_is_lightweight(self):
        """ProductListItem валидируется из минимального объекта."""
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            cost=Decimal("999.99"),
            status="available",
        )

        item = ProductListItem.model_validate(fake)

        assert item.id == 1
        assert item.name == "Laptop"
        assert item.cost == Decimal("999.99")
        assert item.cover_url is None  # default

    def test_list_item_without_heavy_fields(self):
        """
        ProductListItem НЕ содержит тяжёлых полей.

        ДОКАЗЫВАЕТ: список не тянет description, images, created_at.
        """
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            cost=Decimal("999.99"),
            status="available",
        )

        item = ProductListItem.model_validate(fake)

        assert not hasattr(item, "description")
        assert not hasattr(item, "created_at")
        assert not hasattr(item, "images")

    def test_list_item_accepts_cover_url(self):
        """cover_url подхватывается, если есть."""
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            cost=Decimal("999.99"),
            status="available",
            cover_url="https://cdn/cover.jpg",
        )

        item = ProductListItem.model_validate(fake)

        assert item.cover_url == "https://cdn/cover.jpg"

    def test_list_item_cover_url_defaults_to_none(self):
        """Если у объекта нет cover_url, поле = None."""
        fake = types.SimpleNamespace(
            id=1,
            name="Laptop",
            cost=Decimal("999.99"),
            status="available",
            # cover_url отсутствует
        )

        item = ProductListItem.model_validate(fake)

        assert item.cover_url is None


# ===================== CategoryBrief =====================

class TestCategoryBrief:
    """Контракт вложенной схемы CategoryBrief."""

    def test_category_brief_from_dict(self):
        """Валидация из dict."""
        brief = CategoryBrief(id=10, category_name="Electronics")

        assert brief.id == 10
        assert brief.category_name == "Electronics"

    def test_category_brief_from_orm(self):
        """Валидация из ORM-подобного объекта."""
        fake = types.SimpleNamespace(id=10, category_name="Electronics")

        brief = CategoryBrief.model_validate(fake)

        assert brief.id == 10
        assert brief.category_name == "Electronics"


# ===================== ProductImageBrief =====================

class TestProductImageBrief:
    """Контракт вложенной схемы ProductImageBrief."""

    def test_image_brief_from_dict(self):
        """url передаётся напрямую (не alias)."""
        brief = ProductImageBrief(id=100, url="https://cdn/img.jpg")

        assert brief.id == 100
        assert brief.url == "https://cdn/img.jpg"

    def test_image_brief_serializes_as_url(self):
        """В JSON ключ — url."""
        brief = ProductImageBrief(id=100, url="https://cdn/img.jpg")
        dumped = brief.model_dump()

        assert dumped == {"id": 100, "url": "https://cdn/img.jpg"}