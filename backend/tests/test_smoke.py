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