"""
Категории: публичное чтение + админский CRUD.

Публичные:
- GET /categories          — плоский список (ORDER BY path)
- GET /categories/tree     — дерево (рекурсивный)

Админские (require_roles ADMIN, MODERATOR):
- POST   /admin/categories
- PATCH  /admin/categories/{id}
- DELETE /admin/categories/{id}
"""
import logging

from app.api.v1.deps import require_roles
from app.db.enum import UserRole
from app.db.session import get_db
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryTreeResponse,
    CategoryUpdate,
)
from app.services import category_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ============================================================
#  Public
# ============================================================

public_router = APIRouter(prefix="/categories", tags=["categories"])


@public_router.get("", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """
    Плоский список категорий. ORDER BY path — иерархическая сортировка.

    Публичный — без авторизации.
    """
    categories = await category_service.list_categories(db)
    return [
        CategoryResponse(
            id=c.id,
            category_name=c.category_name,
            path=str(c.path),
            parent_id=c.parent_id,
        )
        for c in categories
    ]


@public_router.get("/tree", response_model=list[CategoryTreeResponse])
async def get_category_tree(db: AsyncSession = Depends(get_db)):
    """
    Дерево категорий с вложенными children.

    Публичный — без авторизации.
    """
    return await category_service.get_category_tree(db)


# ============================================================
#  Admin
# ============================================================

admin_router = APIRouter(
    prefix="/admin/categories",
    tags=["admin:categories"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)


@admin_router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создаёт категорию.

    path вычисляется как parent.path + slug(name).
    Ошибки:
    - 422 invalid_parent: parent_id не существует;
    - 409 category_name_taken: конфликт UNIQUE(path) в том же родителе.
    """
    category = await category_service.create_category(db, data)
    return CategoryResponse(
        id=category.id,
        category_name=category.category_name,
        path=str(category.path),
        parent_id=category.parent_id,
    )


@admin_router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    PATCH. Переименование path НЕ меняет. Перемещение каскадно пересчитывает path.

    Ошибки:
    - 404: категория не найдена;
    - 422 self_parent / cycle_detected: перемещение в себя или в потомка;
    - 409 path_conflict: целевой path уже занят.
    """
    category = await category_service.update_category(db, category_id, data)
    if category is None:
        raise HTTPException(404, "Category not found")
    return CategoryResponse(
        id=category.id,
        category_name=category.category_name,
        path=str(category.path),
        parent_id=category.parent_id,
    )


@admin_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Hard-delete. Только если нет детей и товаров.

    Ошибки:
    - 404: категория не найдена;
    - 409 category_has_children: есть дочерние категории;
    - 409 category_has_products: есть товары (включая soft-deleted).
    """
    deleted = await category_service.delete_category(db, category_id)
    if not deleted:
        raise HTTPException(404, "Category not found")
    return None