# tests/test_category_service.py
"""
Сервисные тесты category_service.

Проверяют:
- _slugify: транслитерация, нормализация, границы;
- create_category: path из parent.path + slug, конфликты, invalid parent;
- update_category: переименование (path НЕ меняется), перемещение (каскад);
- _move_category: self-parent, цикл (через <@), конфликт UNIQUE;
- delete_category: с детьми → 409, с товарами → 409, hard-delete;
- list_categories: сортировка по path;
- get_category_tree: вложенность.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy_utils import Ltree

from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services import category_service
from app.services.category_service import _slugify


# ============================================================
#  _slugify
# ============================================================

class TestSlugify:
    """Транслитерация и нормализация в ltree-метку."""

    def test_lowercases_ascii(self):
        assert _slugify("Electronics") == "electronics"

    def test_transliterates_cyrillic(self):
        assert _slugify("Ноутбуки") == "noutbuki"

    def test_spaces_and_symbols_to_underscore(self):
        assert _slugify("Test-Category 2026!") == "test_category_2026"

    def test_multiple_symbols_collapse(self):
        """Подряд идущие символы → один _."""
        assert _slugify("a    b") == "a_b"

    def test_strips_leading_trailing_underscores(self):
        assert _slugify("  hello  ") == "hello"

    def test_mixed_cyrillic_ascii(self):
        # «Игровая Laptop 2026»
        assert _slugify("Игровая Laptop 2026") == "igrovaya_laptop_2026"

    def test_digits_kept(self):
        assert _slugify("123") == "123"

    def test_max_length_63(self):
        """ltree-метка ограничена 63 символами."""
        long_name = "a" * 100
        assert len(_slugify(long_name)) == 63

    def test_empty_raises_422(self):
        with pytest.raises(HTTPException) as exc:
            _slugify("   ")
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "invalid_category_name"

    def test_only_symbols_raises_422(self):
        with pytest.raises(HTTPException) as exc:
            _slugify("!!!")
        assert exc.value.status_code == 422


# ============================================================
#  create_category
# ============================================================

class TestCreateCategory:
    """Создание категории."""

    @pytest.mark.asyncio
    async def test_root_category(self, db_session):
        cat = await category_service.create_category(
            db_session, CategoryCreate(category_name="Electronics")
        )
        assert cat.id is not None
        assert cat.parent_id is None
        assert str(cat.path) == "electronics"
        assert cat.category_name == "Electronics"

    @pytest.mark.asyncio
    async def test_child_category(
        self, db_session, category_root: Category
    ):
        cat = await category_service.create_category(
            db_session,
            CategoryCreate(category_name="Laptops", parent_id=category_root.id),
        )
        assert cat.parent_id == category_root.id
        assert str(cat.path) == "electronics.laptops"

    @pytest.mark.asyncio
    async def test_grandchild(self, db_session, category_child: Category):
        cat = await category_service.create_category(
            db_session,
            CategoryCreate(category_name="Gaming", parent_id=category_child.id),
        )
        assert str(cat.path) == "electronics.laptops.gaming"

    @pytest.mark.asyncio
    async def test_cyrillic_name_transliterated(self, db_session):
        cat = await category_service.create_category(
            db_session, CategoryCreate(category_name="Ноутбуки")
        )
        assert str(cat.path) == "noutbuki"
        assert cat.category_name == "Ноутбуки"   # человекочитаемое сохранено

    @pytest.mark.asyncio
    async def test_invalid_parent_422(self, db_session):
        with pytest.raises(HTTPException) as exc:
            await category_service.create_category(
                db_session,
                CategoryCreate(category_name="Orphan", parent_id=999999),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "invalid_parent"

    @pytest.mark.asyncio
    async def test_duplicate_name_same_parent_409(
        self, db_session, category_root: Category
    ):
        """UNIQUE(path) — второй Laptops под electronics → 409."""
        await category_service.create_category(
            db_session,
            CategoryCreate(category_name="Laptops", parent_id=category_root.id),
        )
        with pytest.raises(HTTPException) as exc:
            await category_service.create_category(
                db_session,
                CategoryCreate(category_name="Laptops", parent_id=category_root.id),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "category_name_taken"

    @pytest.mark.asyncio
    async def test_same_name_different_parents_ok(
        self, db_session, category_root: Category
    ):
        """Laptops под electronics и под furniture — разные path, ок."""
        other_root = await category_service.create_category(
            db_session, CategoryCreate(category_name="Furniture")
        )
        c1 = await category_service.create_category(
            db_session,
            CategoryCreate(category_name="Laptops", parent_id=category_root.id),
        )
        c2 = await category_service.create_category(
            db_session,
            CategoryCreate(category_name="Laptops", parent_id=other_root.id),
        )
        assert str(c1.path) == "electronics.laptops"
        assert str(c2.path) == "furniture.laptops"


# ============================================================
#  list_categories
# ============================================================

class TestListCategories:
    """Плоский список с сортировкой по path."""

    @pytest.mark.asyncio
    async def test_empty(self, db_session):
        cats = await category_service.list_categories(db_session)
        assert cats == []

    @pytest.mark.asyncio
    async def test_hierarchical_order(
        self,
        db_session,
        category_root,
        category_child,
        category_grandchild,
        category_for_admin,
    ):
        """ORDER BY path: electronics < electronics.laptops
        < electronics.laptops.gaming < furniture."""
        cats = await category_service.list_categories(db_session)
        paths = [str(c.path) for c in cats]
        assert paths == [
            "electronics",
            "electronics.laptops",
            "electronics.laptops.gaming",
            "furniture",
        ]


# ============================================================
#  get_category_tree
# ============================================================

class TestGetCategoryTree:
    """Дерево категорий."""

    @pytest.mark.asyncio
    async def test_empty(self, db_session):
        tree = await category_service.get_category_tree(db_session)
        assert tree == []

    @pytest.mark.asyncio
    async def test_nested_tree(
        self,
        db_session,
        category_root,
        category_child,
        category_grandchild,
    ):
        """Корень → child → grandchild."""
        tree = await category_service.get_category_tree(db_session)
        assert len(tree) == 1
        root = tree[0]
        assert root["category_name"] == "Electronics"
        assert len(root["children"]) == 1

        child = root["children"][0]
        assert child["category_name"] == "Laptops"
        assert len(child["children"]) == 1

        grand = child["children"][0]
        assert grand["category_name"] == "Gaming Laptops"
        assert grand["children"] == []

    @pytest.mark.asyncio
    async def test_multiple_roots(
        self, db_session, category_root, category_for_admin
    ):
        tree = await category_service.get_category_tree(db_session)
        assert len(tree) == 2
        names = {n["category_name"] for n in tree}
        assert names == {"Electronics", "Furniture"}


# ============================================================
#  update_category — переименование
# ============================================================

class TestRenameCategory:
    """Переименование: path НЕ меняется (стабильные URL)."""

    @pytest.mark.asyncio
    async def test_rename_keeps_path(
        self, db_session, category_root: Category
    ):
        old_path = str(category_root.path)
        cat = await category_service.update_category(
            db_session,
            category_root.id,
            CategoryUpdate(category_name="Электроника"),
        )
        assert cat is not None
        assert cat.category_name == "Электроника"
        assert str(cat.path) == old_path    # ← path не пересчитан

    @pytest.mark.asyncio
    async def test_rename_child_does_not_affect_path(
        self, db_session, category_child: Category
    ):
        cat = await category_service.update_category(
            db_session,
            category_child.id,
            CategoryUpdate(category_name="Ноутбуки"),
        )
        assert str(cat.path) == "electronics.laptops"

    @pytest.mark.asyncio
    async def test_rename_missing_returns_none(self, db_session):
        result = await category_service.update_category(
            db_session, 999999, CategoryUpdate(category_name="X")
        )
        assert result is None


# ============================================================
#  update_category — перемещение
# ============================================================

class TestMoveCategory:
    """Перемещение: каскадное обновление path."""

    @pytest.mark.asyncio
    async def test_move_to_other_root(
        self, db_session, category_child: Category, category_for_admin: Category
    ):
        """electronics.laptops → furniture.laptops."""
        cat = await category_service.update_category(
            db_session,
            category_child.id,
            CategoryUpdate(parent_id=category_for_admin.id),
        )
        assert cat is not None
        assert cat.parent_id == category_for_admin.id
        assert str(cat.path) == "furniture.laptops"

    @pytest.mark.asyncio
    async def test_move_cascades_to_descendants(
        self, db_session, category_child, category_grandchild
    ):
        """
        Перемещаем electronics.laptops под furniture → потомок
        electronics.laptops.gaming становится furniture.laptops.gaming.
        """
        # Создаём furniture
        furniture = await category_service.create_category(
            db_session, CategoryCreate(category_name="Furniture")
        )

        await category_service.update_category(
            db_session,
            category_child.id,
            CategoryUpdate(parent_id=furniture.id),
        )
        # Обновляем объект из БД
        await db_session.refresh(category_grandchild)
        assert str(category_grandchild.path) == "furniture.laptops.gaming"

    @pytest.mark.asyncio
    async def test_move_to_root(
        self, db_session, category_child: Category
    ):
        """electronics.laptops → laptops (корневая)."""
        cat = await category_service.update_category(
            db_session,
            category_child.id,
            CategoryUpdate(parent_id=None),
        )
        assert cat is not None
        assert cat.parent_id is None
        assert str(cat.path) == "laptops"

    @pytest.mark.asyncio
    async def test_self_parent_422(
        self, db_session, category_root: Category
    ):
        with pytest.raises(HTTPException) as exc:
            await category_service.update_category(
                db_session,
                category_root.id,
                CategoryUpdate(parent_id=category_root.id),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "self_parent"

    @pytest.mark.asyncio
    async def test_cycle_detected_422(
        self, db_session, category_root, category_child, category_grandchild
    ):
        """
        Переместить electronics в своего внука gaming → цикл.
        Проверяется через ltree <@, а не startswith.
        """
        with pytest.raises(HTTPException) as exc:
            await category_service.update_category(
                db_session,
                category_root.id,
                CategoryUpdate(parent_id=category_grandchild.id),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "cycle_detected"

    @pytest.mark.asyncio
    async def test_move_conflict_409(
        self, db_session, category_root, category_child
    ):
        """
        У electronics есть electronics.laptops.
        Пробуем переместить category_child под root с тем же slug → конфликт.
        Но мы не можем — electronics.laptops уже занято.
        Проверим по-другому: создаём в другом месте, переименовываем...

        Проще: пытаемся переместить electronics.laptops в furniture,
        где уже есть furniture.laptops.
        """
        furniture = await category_service.create_category(
            db_session, CategoryCreate(category_name="Furniture")
        )
        # furniture.laptops уже существует
        await category_service.create_category(
            db_session,
            CategoryCreate(category_name="Laptops", parent_id=furniture.id),
        )

        with pytest.raises(HTTPException) as exc:
            await category_service.update_category(
                db_session,
                category_child.id,
                CategoryUpdate(parent_id=furniture.id),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "path_conflict"


# ============================================================
#  delete_category
# ============================================================

class TestDeleteCategory:
    """Hard-delete с проверками."""

    @pytest.mark.asyncio
    async def test_delete_leaf_no_products(
        self, db_session, category_grandchild: Category
    ):
        """Удаление листа без товаров — успешно."""
        result = await category_service.delete_category(
            db_session, category_grandchild.id
        )
        assert result is True

        # Больше нет
        found = await db_session.get(Category, category_grandchild.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_missing_returns_false(self, db_session):
        result = await category_service.delete_category(db_session, 999999)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_with_children_409(
    self, db_session, category_root, category_child):
        """У root есть child → 409."""
        with pytest.raises(HTTPException) as exc:
            await category_service.delete_category(db_session, category_root.id)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "category_has_children"

    @pytest.mark.asyncio
    async def test_delete_with_products_409(
        self, db_session, category_grandchild: Category
    ):
        """У category_grandchild есть товар → 409."""
        db_session.add(Product(
            name="Gaming Laptop",
            description="Test",
            cost=Decimal("2000.00"),
            category_id=category_grandchild.id,
        ))
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await category_service.delete_category(
                db_session, category_grandchild.id
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "category_has_products"

    @pytest.mark.asyncio
    async def test_delete_with_soft_deleted_product_409(
        self, db_session, category_grandchild: Category
    ):
        """
        Soft-deleted товар всё равно блокирует удаление (FK RESTRICT).
        """
        from datetime import datetime, timezone

        product = Product(
            name="Deleted Laptop",
            description="Test",
            cost=Decimal("2000.00"),
            category_id=category_grandchild.id,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(product)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await category_service.delete_category(
                db_session, category_grandchild.id
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "category_has_products"