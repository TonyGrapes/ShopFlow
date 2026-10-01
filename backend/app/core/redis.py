# app/core/redis.py
"""
Асинхронный Redis-клиент.

Жизненный цикл:
- один клиент на процесс (lru_cache);
- lazy — не создаётся при импорте модуля;
- health-check встроен.
"""
import logging
from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis() -> Redis:
    """
    Создаёт асинхронный Redis-клиент.

    URL склеивается из REDIS_URL + REDIS_PASSWORD (property в Settings).
    """
    settings = get_settings()
    url = settings.redis_url_with_password

    client = Redis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,          # bytes → str автоматически
        socket_timeout=3.0,             # не ждём вечно
        socket_connect_timeout=3.0,
        retry_on_timeout=True,
        health_check_interval=30,       # пингует Redis
        max_connections=20,             # пул соединений
    )
    logger.info("Redis client initialized: %s", settings.REDIS_URL)
    return client


async def close_redis() -> None:
    """
    Закрывает клиент. Вызывается в lifespan при shutdown.
    """
    client = get_redis()
    await client.close()
    get_redis.cache_clear()
    logger.info("Redis client closed")