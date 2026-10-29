# app/api/v1/endpoints/cart.py
"""
Корзина: гибридная (гость в Redis, юзер в Postgres).

Контракт:
- Гость идентифицируется cookie `shopflow_cart_session`.
- Юзер — Bearer access-токен.
- Все мутации возвращают полное состояние корзины (CartResponse) —
  клиент не делает лишний GET.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import (
    CartOwner,
    get_cart_owner,
    get_guest_cart_store,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartResponse
from app.schemas.promo import PromoCodePreviewRequest, PromoCodePreviewResponse
from app.services import cart_service, promo_service
from app.services.cart_service import GuestCartStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart", tags=["cart"])


async def _read_cart(
    owner: CartOwner,
    db: AsyncSession,
    guest_store: GuestCartStore,
) -> CartResponse:
    """Единая точка чтения — для guest и user."""
    if owner.is_guest:
        assert owner.session_id is not None
        return await cart_service.get_guest_cart_as_response(
            db=db,
            guest_store=guest_store,
            session_id=owner.session_id,
        )
    assert owner.user_id is not None
    return await cart_service.get_user_cart(db, owner.user_id)


# ============================================================
#  GET /cart
# ============================================================

@router.get("", response_model=CartResponse)
async def get_cart(
    owner: CartOwner = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
    guest_store: GuestCartStore = Depends(get_guest_cart_store),
):
    """
    Читает корзину.

    Для гостя — fail-open при недоступности Redis (пустая корзина
    вместо 500). Для юзера — обычное чтение из БД.
    """
    return await _read_cart(owner, db, guest_store)


# ============================================================
#  POST /cart/items
# ============================================================

@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_item(
    data: CartItemCreate,
    owner: CartOwner = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
    guest_store: GuestCartStore = Depends(get_guest_cart_store),
):
    """
    Добавляет позицию. Идемпотентно: если товар уже в корзине —
    увеличивает количество.

    Статусы:
    - 201: успех.
    - 404: товар не найден / удалён.
    - 409: превышен лимит позиций.
    - 503: Redis недоступен (только для гостя).
    """
    if owner.is_guest:
        assert owner.session_id is not None
        product = await cart_service.get_available_product(db, data.product_id)
        if product is None:
            raise HTTPException(404, "Product not found")

        try:
            await guest_store.upsert_item(
                session_id=owner.session_id,
                product_id=data.product_id,
                quantity_delta=data.quantity,
                product_cost=product.cost,
                max_items=get_settings().GUEST_CART_MAX_ITEMS,
            )
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        except Exception:
            logger.exception("Redis failed on cart add")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Cart storage unavailable",
            ) from None
    else:
        assert owner.user_id is not None
        try:
            await cart_service.add_item_to_user_cart(
                db=db,
                user_id=owner.user_id,
                product_id=data.product_id,
                quantity=data.quantity,
            )
        except LookupError as e:
            raise HTTPException(404, str(e)) from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    return await _read_cart(owner, db, guest_store)


# ============================================================
#  PATCH /cart/items/{product_id}
# ============================================================

@router.patch("/items/{product_id}", response_model=CartResponse)
async def update_item(
    product_id: int,
    data: CartItemUpdate,
    owner: CartOwner = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
    guest_store: GuestCartStore = Depends(get_guest_cart_store),
):
    """
    Устанавливает абсолютное количество. quantity=0 → удаляет позицию.

    Статусы:
    - 200: успех (в т.ч. если позиции не было — операция идемпотентна для гостя).
    - 404: позиции нет (только для юзера — для гостя это no-op).
    - 503: Redis недоступен.
    """
    if owner.is_guest:
        assert owner.session_id is not None
        try:
            await guest_store.set_quantity(
                owner.session_id, product_id, data.quantity
            )
        except Exception:
            logger.exception("Redis failed on cart update")
            raise HTTPException(503, "Cart storage unavailable") from None
    else:
        assert owner.user_id is not None
        found = await cart_service.set_user_cart_item_quantity(
            db=db,
            user_id=owner.user_id,
            product_id=product_id,
            quantity=data.quantity,
        )
        if not found:
            raise HTTPException(404, "Cart item not found")

    return await _read_cart(owner, db, guest_store)

# ============================================================
#  POST /cart/apply-promo — preview промокода
# ============================================================

@router.post("/apply-promo", response_model=PromoCodePreviewResponse)
async def apply_promo_preview(
    data: PromoCodePreviewRequest,
    owner: CartOwner = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
    guest_store: GuestCartStore = Depends(get_guest_cart_store),
):
    """
    Предпросмотр применения промокода.

    НЕ мутирует: used_count не инкрементируется. Только валидация
    и расчёт скидки для текущей корзины.

    Финальная валидация происходит в POST /orders — потому что
    между preview и заказом могут измениться цены, промокод
    истечь или кто-то исчерпать лимит.

    Статусы:
    - 200: промокод валиден, возвращаем расчёт.
    - 422 empty_cart: корзина пуста, применять не к чему.
    - 422 invalid_promo: код невалиден (reason: not_found,
      not_yet_active, expired, min_order_amount).
    - 401: битый Bearer (не маскируем под гостя).
    - 503: Redis недоступен (только для гостя).
    """
    # Читаем корзину — используем ту же логику, что в GET /cart
    cart = await _read_cart(owner, db, guest_store)

    if cart.total_items == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "empty_cart",
                "message": "Cart is empty, nothing to apply promo to",
            },
        )

    # Валидация + расчёт. Без reserve.
    promo, discount = await promo_service.validate_and_calculate(
        db=db,
        code=data.code,
        subtotal=cart.total_cost,
    )

    final_total = cart.total_cost - discount

    return PromoCodePreviewResponse(
        code=promo.code,
        discount_type=promo.discount_type,
        discount_value=f"{promo.discount_value:.2f}",
        subtotal=cart.total_cost,
        discount_amount=discount,
        final_total=final_total,
    )

# ============================================================
#  DELETE /cart/items/{product_id}
# ============================================================

@router.delete("/items/{product_id}", response_model=CartResponse)
async def remove_item(
    product_id: int,
    owner: CartOwner = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
    guest_store: GuestCartStore = Depends(get_guest_cart_store),
):
    """
    Удаляет позицию.

    Для гостя идемпотентно (нет позиции — вернёт 200 с текущей корзиной).
    Для юзера — 404, если позиции нет.
    """
    if owner.is_guest:
        assert owner.session_id is not None
        try:
            await guest_store.remove_item(owner.session_id, product_id)
        except Exception:
            logger.exception("Redis failed on cart remove")
            raise HTTPException(503, "Cart storage unavailable") from None
    else:
        assert owner.user_id is not None
        found = await cart_service.remove_user_cart_item(
            db=db, user_id=owner.user_id, product_id=product_id
        )
        if not found:
            raise HTTPException(404, "Cart item not found")

    return await _read_cart(owner, db, guest_store)


# ============================================================
#  DELETE /cart — очистка
# ============================================================

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    owner: CartOwner = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
    guest_store: GuestCartStore = Depends(get_guest_cart_store),
):
    """Полная очистка корзины. Идемпотентно."""
    if owner.is_guest:
        assert owner.session_id is not None
        await guest_store.clear(owner.session_id)
    else:
        assert owner.user_id is not None
        await cart_service.clear_user_cart(db, owner.user_id)
    return None