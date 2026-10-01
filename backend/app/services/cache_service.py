# app/services/cache_service.py
"""
Обёртка над Redis для кэширования JSON-сериализованных ответов.

Принципы:
- НЕ сериализуем ORM-объекты — только Pydantic-схемы через model_dump.
- НЕ используем pickle — только JSON (безопасность + версионная независимость).
- Ошибки кэша НЕ ломают основной запрос — всегда fallback к БД.
"""
import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def get_json(self, key: str) -> Optional[Any]:
        """
        Читает JSON из кэша.

        ✅ Возвращает None при отсутствии ключа.
        ✅ Возвращает None при ошибке Redis — не ломаем запрос.
        ✅ Возвращает None при битом JSON — кэш мимо.
        """
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Cache: invalid JSON at key=%s, ignoring", key)
            return None
        except Exception:
            logger.exception("Cache: read failed at key=%s", key)
            return None

    async def set_json(
        self, key: str, value: Any, ttl_seconds: int
    ) -> None:
        """
        Пишет JSON в кэш.

        Decimal → строка через `default=str`.
        datetime → ISO 8601 через `default=str`.
        """
        try:
            payload = json.dumps(value, default=str, ensure_ascii=False)
            await self._redis.set(key, payload, ex=ttl_seconds)
        except Exception:
            # Ошибка записи в кэш — не критично, продолжаем
            logger.exception("Cache: write failed at key=%s", key)

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception:
            logger.exception("Cache: delete failed at key=%s", key)

    async def delete_by_pattern(self, pattern: str) -> int:
        """
        Инвалидация по шаблону через SCAN.

        ✅ SCAN не блокирует Redis (в отличие от KEYS).
        ✅ Возвращает число удалённых ключей.
        """
        deleted = 0
        try:
            # SCAN итератор — не блокирует сервер
            async for key in self._redis.scan_iter(match=pattern, count=100):
                await self._redis.delete(key)
                deleted += 1
        except Exception:
            logger.exception(
                "Cache: delete_by_pattern failed for %s", pattern
            )
        return deleted