# app/api/v1/endpoints/favorites.py
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import User, get_current_active_user
from app.db.session import get_db
from app.models.favorite import Favorite
from app.models.product import Product
from app.schemas.favorite import FavoriteCreate, FavoriteResponse
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/favorites", tags=["favorites"])


def _serialize(fav: Favorite, product: Product) -> FavoriteResponse:
    """
    ✅ Сериализация. Обрати внимание: product.cover_key требует
    предзагруженного Product.images — мы гарантируем это в каждом SELECT.
    """
    storage = get_storage()
    return FavoriteResponse(
        id=fav.id,
        product_id=product.id,
        product_name=product.name,
        cover_url=storage.get_url(product.cover_key) if product.cover_key else None,
        cost=f"{product.cost:.2f}",
        status=product.status.value,
        created_at=fav.created_at,
    )


# ============================================================
#  GET /favorites
# ============================================================

@router.get("", response_model=list[FavoriteResponse])
async def list_favorites(
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Список избранного. Soft-deleted товары отфильтрованы."""
    result = await db.execute(
        select(Favorite, Product)
        .join(Product, Product.id == Favorite.product_id)
        .where(
            Favorite.user_id == current.id,
            Product.deleted_at.is_(None),
        )
        .options(selectinload(Product.images))       # ✅ чтобы cover_key не дёргал lazy load
        .order_by(Favorite.created_at.desc())
    )
    rows = result.all()
    return [_serialize(fav, prod) for fav, prod in rows]


# ============================================================
#  POST /favorites
# ============================================================

@router.post("", response_model=FavoriteResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    data: FavoriteCreate,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Идемпотентно: если товар уже в избранном — возвращает существующую запись.
    """
    product = await db.get(Product, data.product_id)
    if product is None or product.deleted_at is not None:
        raise HTTPException(404, "Product not found")

    # Ищем существующее избранное
    existing = (await db.execute(
        select(Favorite).where(
            Favorite.user_id == current.id,
            Favorite.product_id == data.product_id,
        )
    )).scalar_one_or_none()

    if existing is not None:
        # Идемпотентно: возвращаем то, что уже есть (с корректной cover_url)
        # Перезагружаем product с images, чтобы cover_key работал
        product = (await db.execute(
            select(Product)
            .where(Product.id == data.product_id)
            .options(selectinload(Product.images))
        )).scalar_one()
        return _serialize(existing, product)

    fav = Favorite(user_id=current.id, product_id=data.product_id)
    db.add(fav)
    await db.flush()
    await db.refresh(fav)

    # Перезагружаем product с images для сериализации
    product = (await db.execute(
        select(Product)
        .where(Product.id == data.product_id)
        .options(selectinload(Product.images))
    )).scalar_one()

    return _serialize(fav, product)


# ============================================================
#  DELETE /favorites/{product_id}
# ============================================================

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    product_id: int,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Удаляет позицию из избранного. 404, если её нет."""
    fav = (await db.execute(
        select(Favorite).where(
            Favorite.user_id == current.id,
            Favorite.product_id == product_id,
        )
    )).scalar_one_or_none()

    if fav is None:
        raise HTTPException(404, "Favorite not found")

    await db.delete(fav)
    await db.flush()
    return None