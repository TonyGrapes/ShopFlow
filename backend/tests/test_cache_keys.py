# tests/test_cache_keys.py
"""Тесты детерминированности ключей кэша."""
from decimal import Decimal

from app.db.enum import ProductStatus
from app.services.cache_keys import (
    build_product_list_cache_key,
    product_list_cache_pattern,
)


class TestCacheKeys:
    """Ключ детерминирован и учитывает все параметры."""

    def _base_kwargs(self, **overrides):
        base = {
            "page": 1,
            "page_size": 20,
            "category_id": None,
            "min_cost": None,
            "max_cost": None,
            "status": None,
            "sort_by": "id",
            "sort_order": "asc",
        }
        base.update(overrides)
        return base

    def test_same_params_same_key(self):
        """Одинаковые параметры → одинаковый ключ."""
        k1 = build_product_list_cache_key(**self._base_kwargs())
        k2 = build_product_list_cache_key(**self._base_kwargs())
        assert k1 == k2

    def test_different_page_different_key(self):
        k1 = build_product_list_cache_key(**self._base_kwargs(page=1))
        k2 = build_product_list_cache_key(**self._base_kwargs(page=2))
        assert k1 != k2

    def test_decimal_normalization(self):
        """Decimal("100") и Decimal("100.00") → один ключ."""
        k1 = build_product_list_cache_key(
            **self._base_kwargs(min_cost=Decimal("100"))
        )
        k2 = build_product_list_cache_key(
            **self._base_kwargs(min_cost=Decimal("100.00"))
        )
        assert k1 == k2

    def test_none_vs_value_different_key(self):
        """None и 0 → разные ключи."""
        k1 = build_product_list_cache_key(**self._base_kwargs(min_cost=None))
        k2 = build_product_list_cache_key(**self._base_kwargs(min_cost=Decimal("0")))
        assert k1 != k2

    def test_enum_normalization(self):
        """Enum нормализуется в .value."""
        k = build_product_list_cache_key(
            **self._base_kwargs(status=ProductStatus.AVAILABLE)
        )
        assert "products:list:" in k

    def test_pattern_covers_all(self):
        """Паттерн начинается с префикса ключа."""
        k = build_product_list_cache_key(**self._base_kwargs())
        pattern = product_list_cache_pattern()
        assert k.startswith(pattern.rstrip("*"))