# tests/test_smoke.py
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Приложение отвечает на healthcheck (БД + Redis + MinIO)."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["redis"] == "connected"
    assert data["minio"] == "connected"

@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Приложение отвечает на корневой эндпоинт."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "ShopFlow API" in response.json()["message"]


@pytest.mark.asyncio
async def test_refund_reason_constraint_exists(client, db_session):
    """✅ Модель содержит chk_refund_reason (create_all его создаёт)."""
    from sqlalchemy import text

    result = await db_session.execute(
        text("""
            SELECT conname FROM pg_constraint
            WHERE conname = 'chk_refund_reason'
        """)
    )
    assert result.scalar_one_or_none() == "chk_refund_reason"

@pytest.mark.asyncio
async def test_docs_available_in_dev(client):
    """CFG-002: в dev /docs доступен."""
    response = await client.get("/docs")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_openapi_available_in_dev(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_health_unhealthy_when_redis_down(
    client, mock_storage, monkeypatch
):
    """OBS-003: если Redis недоступен — 503, но с детализацией."""
    from unittest.mock import AsyncMock, Mock

    from app.core.redis import get_redis

    broken_redis = Mock()
    broken_redis.ping = AsyncMock(side_effect=Exception("Redis down"))

    # Переопределяем override для этого теста
    from app.main import app as fastapi_app
    fastapi_app.dependency_overrides[get_redis] = lambda: broken_redis

    response = await client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["redis"] == "unavailable"
    assert body["database"] == "connected"
    assert body["minio"] == "connected"