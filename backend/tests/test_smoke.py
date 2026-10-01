# tests/test_smoke.py
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Приложение отвечает на healthcheck."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Приложение отвечает на корневой эндпоинт."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "ShopFlow API" in response.json()["message"]