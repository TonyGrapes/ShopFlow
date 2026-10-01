# tests/test_cache_service.py
import json

import fakeredis.aioredis
import pytest
import pytest_asyncio
from app.services.cache_service import CacheService


@pytest_asyncio.fixture
async def real_cache():
    """Реальный CacheService поверх fakeredis — не мок."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield CacheService(redis)
    finally:
        await redis.aclose()


class TestCacheServiceAgainstRealRedis:
    """Тесты поверх настоящего Redis API (fakeredis)."""

    @pytest.mark.asyncio
    async def test_set_get_roundtrip_with_decimal(self, real_cache):
        """✅ Decimal сериализуется через default=str."""
        from decimal import Decimal
        await real_cache.set_json("k", {"price": Decimal("199.99")}, ttl_seconds=60)
        result = await real_cache.get_json("k")
        assert result == {"price": "199.99"}   # str

    @pytest.mark.asyncio
    async def test_broken_json_returns_none(self, real_cache):
        """✅ Битый JSON → None, не падаем."""
        await real_cache._redis.set("k", "not-json-at-all")
        result = await real_cache.get_json("k")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_by_pattern_uses_scan(self, real_cache):
        """✅ SCAN не блокирует; паттерн удаляет только совпавшие."""
        await real_cache.set_json("products:list:a", 1, ttl_seconds=60)
        await real_cache.set_json("products:list:b", 2, ttl_seconds=60)
        await real_cache.set_json("other:k", 3, ttl_seconds=60)

        deleted = await real_cache.delete_by_pattern("products:list:*")
        assert deleted == 2
        assert await real_cache.get_json("products:list:a") is None
        assert await real_cache.get_json("other:k") == 3

    @pytest.mark.asyncio
    async def test_redis_down_returns_none(self):
        """✅ Redis упал → get_json возвращает None, не бросает."""
        # Эмулируем отказ: закрываем клиент
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        await redis.aclose()
        cache = CacheService(redis)
        result = await cache.get_json("k")
        assert result is None