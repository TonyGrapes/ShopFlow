# app/services/cart_service.py
"""
Гибридная корзина.

- Гость: Redis-строка `cart:{session_id}` с JSON.
- Пользователь: PostgreSQL, таблица `cart_items`.
- Merge при логине: max(quantity) по позициям.
- Снимок цены `product_cost` на момент добавления.
- Soft-deleted товары фильтруются при чтении.

Принципы проекта:
- Сервисы НЕ коммитят — commit в get_db.
- Redis-отказ: fail-open для чтения, fail-closed для записи.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.enum import ProductStatus
from app.models.cart_item import CartItem
from app.models.product import Product
from app.schemas.cart import CartItemResponse, CartResponse
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)


# ============================================================
#  Dataclass для guest-cart
# ============================================================

@dataclass
class GuestCartItem:
    product_id: int
    quantity: int
    product_cost: str           # Decimal сериализуем как строку
    added_at: str               # ISO 8601


@dataclass
class GuestCart:
    items: list[GuestCartItem] = field(default_factory=list)
    updated_at: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "items": [item.__dict__ for item in self.items],
                "updated_at": self.updated_at,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "GuestCart":
        data = json.loads(raw)
        items = [GuestCartItem(**it) for it in data.get("items", [])]
        return cls(items=items, updated_at=data.get("updated_at", ""))


# ============================================================
#  Redis-обёртка для guest-cart
# ============================================================

class GuestCartStore:
    """
    Хранилище гостевой корзины в Redis.

    Все мутации — read-modify-write. Атомарность достигается за счёт
    того, что операции над одной сессией идут последовательно на
    одном соединении (redis-py не параллелит их внутри запроса).
    Для продакшена с конкурентными запросами от одной сессии —
    обернуть в Lua-скрипт, но для текущего объёма — приемлемо.
    """

    def __init__(self, redis: Redis):
        self._redis = redis

    def _key(self, session_id: str) -> str:
        return f"cart:{session_id}"

    async def get(self, session_id: str) -> GuestCart:
        """fail-open: при ошибке Redis возвращаем пустую корзину."""
        try:
            raw = await self._redis.get(self._key(session_id))
            if raw is None:
                return GuestCart()
            return GuestCart.from_json(raw)
        except json.JSONDecodeError:
            logger.warning("GuestCart: invalid JSON for %s", session_id)
            return GuestCart()
        except Exception:
            logger.exception("GuestCart: read failed for %s", session_id)
            return GuestCart()

    async def clear(self, session_id: str) -> None:
        """Идемпотентно. Не падаем на ошибке — TTL сработает."""
        try:
            await self._redis.delete(self._key(session_id))
        except Exception:
            logger.exception("GuestCart: clear failed for %s", session_id)

    async def upsert_item(
        self,
        session_id: str,
        product_id: int,
        quantity_delta: int,
        product_cost: Decimal,
        max_items: int,
    ) -> GuestCart:
        """
        Добавляет quantity_delta к позиции. Если позиции нет — создаёт.
        fail-closed: ошибка Redis → пробрасываем, эндпоинт вернёт 503.
        """
        cart = await self.get(session_id)

        now_iso = datetime.now(timezone.utc).isoformat()
        existing = next(
            (it for it in cart.items if it.product_id == product_id), None
        )

        if existing is None:
            if len(cart.items) >= max_items:
                raise ValueError(f"Cart item limit reached: {max_items}")
            cart.items.append(
                GuestCartItem(
                    product_id=product_id,
                    quantity=quantity_delta,
                    product_cost=f"{product_cost:.2f}",
                    added_at=now_iso,
                )
            )
        else:
            existing.quantity += quantity_delta
            if existing.quantity <= 0:
                cart.items = [
                    it for it in cart.items if it.product_id != product_id
                ]

        cart.updated_at = now_iso
        await self._save(session_id, cart)
        return cart

    async def set_quantity(
        self,
        session_id: str,
        product_id: int,
        quantity: int,
    ) -> GuestCart:
        """Абсолютное значение. quantity=0 → удаляет позицию."""
        cart = await self.get(session_id)
        if quantity <= 0:
            cart.items = [
                it for it in cart.items if it.product_id != product_id
            ]
        else:
            existing = next(
                (it for it in cart.items if it.product_id == product_id), None
            )
            if existing is not None:
                existing.quantity = quantity
            # если позиции нет — ничего не делаем

        cart.updated_at = datetime.now(timezone.utc).isoformat()
        await self._save(session_id, cart)
        return cart

    async def remove_item(self, session_id: str, product_id: int) -> GuestCart:
        cart = await self.get(session_id)
        cart.items = [it for it in cart.items if it.product_id != product_id]
        cart.updated_at = datetime.now(timezone.utc).isoformat()
        await self._save(session_id, cart)
        return cart

    async def _save(self, session_id: str, cart: GuestCart) -> None:
        s = get_settings()
        if not cart.items:
            # Пустую корзину не храним — чистим ключ
            await self._redis.delete(self._key(session_id))
            return
        await self._redis.set(
            self._key(session_id),
            cart.to_json(),
            ex=s.GUEST_CART_REDIS_TTL_SECONDS,
        )


# ============================================================
#  Хелперы
# ============================================================

async def get_available_product(
    db: AsyncSession, product_id: int
) -> Optional[Product]:
    """Возвращает продукт, если он существует и не удалён."""
    product = await db.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        return None
    return product


def _serialize_item(
    product: Product,
    quantity: int,
    snapshot_cost: Decimal,
) -> CartItemResponse:
    """Общая сериализация позиции. Используется для guest и user."""
    storage = get_storage()
    return CartItemResponse(
        product_id=product.id,
        name=product.name,
        cover_url=storage.get_url(product.cover_key) if product.cover_key else None,
        quantity=quantity,
        snapshot_cost=snapshot_cost,
        current_cost=product.cost,
        status=product.status,
        is_available=product.status == ProductStatus.AVAILABLE,
    )


# ============================================================
#  Пользовательская корзина (PostgreSQL)
# ============================================================

async def get_user_cart(db: AsyncSession, user_id: int) -> CartResponse:
    """
    Читает корзину юзера с JOIN продуктов.

    Soft-deleted позиции отфильтрованы (hidden_items_count).
    Позиции с товаром в статусе out_of_stock/discontinued —
    отдаются с is_available=false.
    """
    result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .options(
            # ✅ Загружаем product и его images одной цепочкой
            selectinload(CartItem.product).selectinload(Product.images),
        )
        .order_by(CartItem.created_at)
    )
    all_items = result.scalars().all()

    visible: list[CartItemResponse] = []
    hidden = 0
    total_cost = Decimal("0.00")
    total_items = 0

    for ci in all_items:
        product = ci.product
        if product is None or product.deleted_at is not None:
            hidden += 1
            continue

        visible.append(_serialize_item(product, ci.quantity, ci.product_cost))
        total_cost += ci.product_cost * ci.quantity
        total_items += ci.quantity

    return CartResponse(
        items=visible,
        total_items=total_items,
        total_cost=total_cost,
        hidden_items_count=hidden,
    )


async def get_guest_cart_as_response(
    db: AsyncSession,
    guest_store: GuestCartStore,
    session_id: str,
) -> CartResponse:
    """
    Читает guest-cart из Redis и обогащает данными о продуктах.
    Soft-deleted продукты отфильтровываются, hidden_items_count++.
    """
    guest_cart = await guest_store.get(session_id)
    if not guest_cart.items:
        return CartResponse(
            items=[], total_items=0, total_cost=Decimal("0.00"),
            hidden_items_count=0,
        )

    product_ids = [it.product_id for it in guest_cart.items]
    result = await db.execute(
        select(Product)
        .where(Product.id.in_(product_ids))
        .options(selectinload(Product.images))       # ✅ чтобы cover_key не дёргал lazy load
    )
    products_by_id = {p.id: p for p in result.scalars()}

    visible: list[CartItemResponse] = []
    hidden = 0
    total_cost = Decimal("0.00")
    total_items = 0

    for item in guest_cart.items:
        product = products_by_id.get(item.product_id)
        if product is None or product.deleted_at is not None:
            hidden += 1
            continue

        snapshot = Decimal(item.product_cost)
        visible.append(_serialize_item(product, item.quantity, snapshot))
        total_cost += snapshot * item.quantity
        total_items += item.quantity

    return CartResponse(
        items=visible,
        total_items=total_items,
        total_cost=total_cost,
        hidden_items_count=hidden,
    )


# ============================================================
#  Мутации user-cart (PostgreSQL)
# ============================================================

async def add_item_to_user_cart(
    db: AsyncSession,
    user_id: int,
    product_id: int,
    quantity: int,
) -> None:
    """
    Идемпотентный upsert: если позиция есть — увеличивает quantity,
    если нет — создаёт со снимком текущей цены.
    """
    s = get_settings()

    product = await db.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise LookupError(f"Product {product_id} not found")

    existing = await db.get(
        CartItem, {"user_id": user_id, "product_id": product_id}
    )
    if existing is None:
        count = (
            await db.execute(
                select(func.count()).select_from(CartItem)
                .where(CartItem.user_id == user_id)
            )
        ).scalar_one()
        if count >= s.GUEST_CART_MAX_ITEMS:
            raise ValueError(
                f"Cart item limit reached: {s.GUEST_CART_MAX_ITEMS}"
            )

        db.add(
            CartItem(
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                product_cost=product.cost,   # ✅ снимок текущей цены
            )
        )
    else:
        existing.quantity += quantity

    await db.flush()


async def set_user_cart_item_quantity(
    db: AsyncSession,
    user_id: int,
    product_id: int,
    quantity: int,
) -> bool:
    """Абсолютное значение. quantity=0 → удаляет. True — если позиция была."""
    existing = await db.get(
        CartItem, {"user_id": user_id, "product_id": product_id}
    )
    if existing is None:
        return False

    if quantity <= 0:
        await db.delete(existing)
    else:
        existing.quantity = quantity

    await db.flush()
    return True


async def remove_user_cart_item(
    db: AsyncSession,
    user_id: int,
    product_id: int,
) -> bool:
    existing = await db.get(
        CartItem, {"user_id": user_id, "product_id": product_id}
    )
    if existing is None:
        return False
    await db.delete(existing)
    await db.flush()
    return True


async def clear_user_cart(db: AsyncSession, user_id: int) -> int:
    """Удаляет все позиции. Возвращает количество."""
    result = await db.execute(
        delete(CartItem).where(CartItem.user_id == user_id)
    )
    await db.flush()
    return result.rowcount or 0


# ============================================================
#  Merge guest → user
# ============================================================

@dataclass
class MergeResult:
    merged: int = 0
    warnings: list[str] = field(default_factory=list)


async def merge_guest_cart_into_user(
    db: AsyncSession,
    guest_store: GuestCartStore,
    session_id: str,
    user_id: int,
) -> MergeResult:
    """
    Объединяет guest-cart в user-cart. НЕ удаляет guest-cart из Redis —
    это делает BackgroundTask ПОСЛЕ commit'а.
    """
    guest_cart = await guest_store.get(session_id)
    if not guest_cart.items:
        return MergeResult()

    product_ids = [it.product_id for it in guest_cart.items]

    # Один SELECT на продукты, один — на cart_items юзера. Нет N+1.
    products_result = await db.execute(
        select(Product).where(
            Product.id.in_(product_ids),
            Product.deleted_at.is_(None),
        )
    )
    products_by_id = {p.id: p for p in products_result.scalars()}

    existing_result = await db.execute(
        select(CartItem).where(
            CartItem.user_id == user_id,
            CartItem.product_id.in_(product_ids),
        )
    )
    existing_by_pid = {ci.product_id: ci for ci in existing_result.scalars()}

    warnings: list[str] = []
    merged = 0

    for item in guest_cart.items:
        product = products_by_id.get(item.product_id)
        if product is None:
            warnings.append(
                f"Product {item.product_id} no longer available"
            )
            continue

        if product.status != ProductStatus.AVAILABLE:
            warnings.append(
                f"Product '{product.name}' is {product.status.value}"
            )

        existing = existing_by_pid.get(item.product_id)
        guest_qty = item.quantity

        if existing is None:
            db.add(
                CartItem(
                    user_id=user_id,
                    product_id=item.product_id,
                    quantity=guest_qty,
                    product_cost=Decimal(item.product_cost),   # снимок гостя
                )
            )
            merged += 1
        else:
            new_qty = max(existing.quantity, guest_qty)
            if new_qty != existing.quantity:
                existing.quantity = new_qty
                merged += 1

            guest_cost = Decimal(item.product_cost)
            if existing.product_cost != guest_cost:
                warnings.append(
                    f"Price for '{product.name}' differs: "
                    f"in cart {existing.product_cost}, "
                    f"added as guest {guest_cost}"
                )

    await db.flush()
    return MergeResult(merged=merged, warnings=warnings)