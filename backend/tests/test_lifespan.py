"""
TST-010: покрытие lifespan.

ASGITransport (используется в tests/conftest.py::client) НЕ запускает
lifespan — это by design httpx. Поэтому startup/shutdown в app.main.py
(62-101) не исполняются в 614 текущих тестах и coverage их не видит.

Здесь мы программно управляем lifespan через asgi-lifespan.LifespanManager
и мокаем get_redis/get_storage на уровне app.main — чтобы не дёргать
реальный стек.

Покрываем:
- happy path: Redis ping + MinIO ensure_bucket → app.state.minio_ready True
- retry: ensure_bucket падает 3 раза → minio_ready False (fail-soft)
"""
from unittest.mock import AsyncMock, Mock

import pytest
from asgi_lifespan import LifespanManager

from app.main import app


@pytest.fixture
def _reset_lifespan_state():
    """Сбрасывает app.state.minio_ready между тестами.

    LifespanManager выставляет app.state.minio_ready внутри себя; без
    сброса предыдущий тест влияет на следующий (app — глобальный объект).
    """
    original = getattr(app.state, "minio_ready", None)
    yield
    if original is None:
        try:
            del app.state.minio_ready
        except AttributeError:
            pass
    else:
        app.state.minio_ready = original


@pytest.mark.asyncio
async def test_lifespan_happy_path(mocker, _reset_lifespan_state):
    """lifespan executes: Redis ping + ensure_bucket → minio_ready True."""
    fake_redis = Mock()
    fake_redis.ping = AsyncMock(return_value=True)

    fake_storage = Mock()
    fake_storage.ensure_bucket = Mock(return_value=None)

    mocker.patch("app.main.get_redis", return_value=fake_redis)
    mocker.patch("app.main.get_storage", return_value=fake_storage)
    mocker.patch("app.main.close_redis", new=AsyncMock())

    async with LifespanManager(app):
        # Внутри контекста lifespan startup уже выполнен
        fake_redis.ping.assert_awaited_once()
        fake_storage.ensure_bucket.assert_called_once()
        assert app.state.minio_ready is True

    # После shutdown — close_redis вызван
    # (AsyncMock, вызывается через mocker.patch — просто не падаем)


@pytest.mark.asyncio
async def test_lifespan_retries_on_minio_failure(
    mocker, _reset_lifespan_state
):
    """
    ensure_bucket бросает — 3 попытки → fail-soft (minio_ready False).

    asyncio.sleep замокан, чтобы не ждать реальные 2+5+10 = 17 секунд.
    """
    fake_redis = Mock()
    fake_redis.ping = AsyncMock(return_value=True)

    fake_storage = Mock()
    fake_storage.ensure_bucket = Mock(side_effect=Exception("MinIO down"))

    mocker.patch("app.main.get_redis", return_value=fake_redis)
    mocker.patch("app.main.get_storage", return_value=fake_storage)
    mocker.patch("app.main.close_redis", new=AsyncMock())
    mocker.patch("app.main.asyncio.sleep", new=AsyncMock())

    async with LifespanManager(app):
        # 3 попытки: retry_delays = [2, 5, 10]
        assert fake_storage.ensure_bucket.call_count == 3
        # Fail-soft: приложение стартовало, но bucket не готов
        assert app.state.minio_ready is False