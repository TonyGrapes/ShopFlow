"""
Сервис категорий (ltree + parent_id).

Модель:
- parent_id — источник правды (FK self-reference, RESTRICT).
- path — ltree, денормализация для запросов (WHERE path <@ ?).

Инварианты:
- path строится как parent.path + slug(name).
- Переименование НЕ меняет path (стабильные URL).
- Перемещение каскадно обновляет path всех потомков одним UPDATE.
- Нельзя переместить категорию в своего потомка (цикл).
- Hard-delete только если нет детей и товаров.
"""
import logging
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryUpdate

logger = logging.getLogger(__name__)

_CATEGORY_PATH_CONSTRAINT = "uq_categories_path"

# Транслитерация кириллицы → латиница. Минимальный набор для ltree-меток.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _slugify(name: str) -> str:
    """
    Строит ltree-совместимую метку из имени категории.

    - lowercase
    - транслитерация кириллицы
    - всё не [a-z0-9] → '_'
    - обрезка до 63 символов (лимит ltree-метки)
    - 422 если получилось пусто
    """
    lowered = name.lower()
    transliterated = "".join(_TRANSLIT.get(ch, ch) for ch in lowered)
    slug = re.sub(r"[^a-z0-9]+", "_", transliterated).strip("_")
    slug = slug[:63]

    if not slug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_category_name",
                "message": "Category name must contain at least one alphanumeric character",
            },
        )
    return slug


# ============================================================
#  Создание
# ============================================================

async def create_category(
    db: AsyncSession, data: CategoryCreate
) -> Category:
    """
    Создаёт категорию.

    path = parent.path + '.' + slug(name), или slug(name) для корневой.
    """
    parent_path = ""
    if data.parent_id is not None:
        parent = await db.get(Category, data.parent_id)
        if parent is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "invalid_parent",
                    "parent_id": data.parent_id,
                },
            )
        parent_path = str(parent.path)

    slug = _slugify(data.category_name)
    new_path = f"{parent_path}.{slug}" if parent_path else slug

    category = Category(
        parent_id=data.parent_id,
        path=new_path,
        category_name=data.category_name,
    )
    db.add(category)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if _is_path_conflict(exc):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "category_name_taken",
                    "message": "Category with this name already exists under the same parent",
                },
            ) from exc
        logger.exception("Unexpected IntegrityError on create_category")
        raise

    await db.refresh(category)
    return category


# ============================================================
#  Чтение
# ============================================================

async def get_category(
    db: AsyncSession, category_id: int
) -> Optional[Category]:
    return await db.get(Category, category_id)


async def list_categories(db: AsyncSession) -> list[Category]:
    """Плоский список. ORDER BY path — иерархическая сортировка."""
    result = await db.execute(select(Category).order_by(Category.path))
    return list(result.scalars().all())


async def get_category_tree(db: AsyncSession) -> list[dict]:
    """
    Дерево категорий.

    Строим в Python из плоского списка (одна SELECT).
    Возвращает список корневых узлов с вложенными children.
    """
    result = await db.execute(select(Category).order_by(Category.path))
    rows = list(result.scalars().all())

    nodes: dict[int, dict] = {}
    for c in rows:
        nodes[c.id] = {
            "id": c.id,
            "category_name": c.category_name,
            "path": str(c.path),
            "parent_id": c.parent_id,
            "children": [],
        }

    roots: list[dict] = []
    for c in rows:
        node = nodes[c.id]
        if c.parent_id is None:
            roots.append(node)
        else:
            parent = nodes.get(c.parent_id)
            if parent is not None:
                parent["children"].append(node)

    return roots


# ============================================================
#  Обновление (name / parent)
# ============================================================

async def update_category(
    db: AsyncSession, category_id: int, data: CategoryUpdate
) -> Optional[Category]:
    """
    PATCH.

    - category_name: меняет только имя, path остаётся стабильным.
    - parent_id: каскадно пересчитывает path категории и потомков.

    Порядок: сначала move (пересчитывает path по старому имени),
    потом rename (имя меняется, path остаётся).
    """
    category = await db.get(Category, category_id)
    if category is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Перемещение — ДО переименования
    if "parent_id" in update_data and update_data["parent_id"] != category.parent_id:
        await _move_category(db, category, update_data["parent_id"])

    # Переименование (path НЕ пересчитывается — стабильные URL)
    if "category_name" in update_data:
        category.category_name = update_data["category_name"]

    await db.flush()
    await db.refresh(category)
    return category


async def _move_category(
    db: AsyncSession, category: Category, new_parent_id: Optional[int]
) -> None:
    """
    Меняет parent_id и каскадно пересчитывает path.

    Проверки:
    - нельзя быть родителем себе (parent_id == self.id) → 422;
    - нельзя переместить в своего потомка (цикл) → 422;
    - UNIQUE(path) при конфликте → 409.

    Порядок операций:
    1. Проверки (self, cycle).
    2. Raw UPDATE потомков — по старому old_path.
    3. ORM-обновление category (parent_id, path).
    4. flush.
    """
    # 1. Нельзя быть родителем себе
    if new_parent_id == category.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "self_parent", "message": "Category cannot be its own parent"},
        )

    # 2. Новый родитель существует?
    parent_path = ""
    if new_parent_id is not None:
        new_parent = await db.get(Category, new_parent_id)
        if new_parent is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_parent", "parent_id": new_parent_id},
            )
        # 3. Новый родитель не внутри поддерева текущей категории (цикл).
        #    Используем ltree-оператор <@ — точная семантика «descendant or equal».
        #    startswith() дал бы ложные срабатывания (electronics2 vs electronics).
        cycle_check = await db.execute(
            text(
                "SELECT 1 FROM categories "
                "WHERE id = :pid AND path <@ CAST(:cpath AS ltree)"
            ),
            {"pid": new_parent_id, "cpath": str(category.path)},
        )
        if cycle_check.scalar_one_or_none() is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "cycle_detected",
                    "message": "Cannot move category into its own subtree",
                },
            )
        parent_path = str(new_parent.path)

    # 4. Новый path для самой категории (slug от ТЕКУЩЕГО имени —
    #    при переименовании path не меняется, см. решение 2-А)
    slug = _slugify(category.category_name)
    new_path = f"{parent_path}.{slug}" if parent_path else slug
    old_path = str(category.path)

    # 5. Каскадное обновление потомков одним UPDATE.
    #    CAST(:old_path AS ltree) обязателен — nlevel(ltree), иначе Postgres
    #    получит text и не найдёт функцию nlevel(text).
    try:
        await db.execute(
            text("""
                UPDATE categories
                SET path = CAST(
                    CAST(:new_path AS text) || '.' || subpath(path, nlevel(CAST(:old_path AS ltree)))::text
                AS ltree
            )
                WHERE path <@ CAST(:old_path AS ltree) AND id != :cid   
            """),
            {"new_path": new_path, "old_path": old_path, "cid": category.id},
        )
        # Обновляем саму категорию
        category.parent_id = new_parent_id
        category.path = new_path
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if _is_path_conflict(exc):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "path_conflict",
                    "message": "Target path already exists (conflict with another category)",
                },
            ) from exc
        raise


# ============================================================
#  Удаление
# ============================================================

async def delete_category(db: AsyncSession, category_id: int) -> bool:
    """
    Hard-delete. Только если нет детей и товаров.

    - есть дети → 409
    - есть товары (включая soft-deleted) → 409
    """
    category = await db.get(Category, category_id)
    if category is None:
        return False

    # Дети
    has_children = (await db.execute(
        select(func.count()).select_from(Category).where(
            Category.parent_id == category_id
        )
    )).scalar_one()
    if has_children > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "category_has_children",
                "message": "Cannot delete category with subcategories",
            },
        )

    # Товары (включая soft-deleted — FK RESTRICT не даст удалить)
    has_products = (await db.execute(
        select(func.count()).select_from(Product).where(
            Product.category_id == category_id
        )
    )).scalar_one()
    if has_products > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "category_has_products",
                "message": "Cannot delete category with products",
            },
        )

    await db.delete(category)
    await db.flush()
    return True


# ============================================================
#  Утилиты
# ============================================================

def _is_path_conflict(exc: IntegrityError) -> bool:
    """IntegrityError на UNIQUE(path) в categories."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False

    message = str(orig)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) if diag else None

    return (
        constraint_name == _CATEGORY_PATH_CONSTRAINT
        or _CATEGORY_PATH_CONSTRAINT in message
    )