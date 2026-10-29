# app/services/cache_keys.py
"""
Детерминированные ключи для кэша каталога.

Гарантии:
- Один и тот же набор параметров → один и тот же ключ.
- Разные наборы → разные ключи.
- Нормализация типов: None, Decimal, enum приводятся к канону.
"""
import hashlib
from decimal import Decimal

from app.db.enum import ProductStatus

_PREFIX = "products:list"
_NULL_MARKER = "_"          # пустая строка в URL может быть легитимна → используем явный маркер


def _normalize(value) -> str:
    """Приводит значение к канонической строке."""
    if value is None:
        return _NULL_MARKER
    if isinstance(value, Decimal):
        # ✅ Decimal("100") и Decimal("100.00") → "100.00"
        return f"{value:.2f}"
    if isinstance(value, ProductStatus):
        return value.value
    return str(value)


def build_product_list_cache_key(
    *,
    page: int,
    page_size: int,
    category_id: int | None,
    min_cost: Decimal | None,
    max_cost: Decimal | None,
    status: ProductStatus | None,
    sort_by: str,
    sort_order: str,
) -> str:
    """
    Строит ключ вида products:list:<sha256[:16]>.

    Все параметры нормализуются и хешируются.
    Порядок не важен — в каждом слоте явное имя.
    """
    parts = {
        "page": _normalize(page),
        "page_size": _normalize(page_size),
        "category_id": _normalize(category_id),
        "min_cost": _normalize(min_cost),
        "max_cost": _normalize(max_cost),
        "status": _normalize(status),
        "sort_by": _normalize(sort_by),
        "sort_order": _normalize(sort_order),
    }
    # Каноничный порядок: сортируем по имени поля
    canonical = "|".join(f"{k}={v}" for k, v in sorted(parts.items()))

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{_PREFIX}:{digest}"


def product_list_cache_pattern() -> str:
    """Шаблон для инвалидации всех ключей списка."""
    return f"{_PREFIX}:*"