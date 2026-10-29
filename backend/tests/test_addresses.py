# tests/test_addresses.py
"""
Тесты CRUD адресов и инварианта is_default.

Проверяют:
- CRUD для владельца (200/201/204);
- 404 для чужого адреса;
- автоматический сброс is_default с предыдущего (partial unique index);
- идемпотентность set-default;
- инвариант «не больше одного дефолтного адреса у юзера».
"""

import pytest
from sqlalchemy import select

from app.models.address import Address


class TestCreateAddress:
    """POST /addresses."""

    @pytest.mark.asyncio
    async def test_create_basic(self, client, auth_headers):
        response = await client.post(
            "/api/v1/addresses",
            json={
                "address_line1": "ул. Новая, 5",
                "city": "Казань",
                "postal_code": "420000",
                "country": "RU",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["city"] == "Казань"
        assert body["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_with_is_default_resets_previous(
        self, client, auth_headers, address, db_session
    ):
        """Создание нового дефолтного сбрасывает флаг у старого."""
        response = await client.post(
            "/api/v1/addresses",
            json={
                "address_line1": "ул. Новейшая, 7",
                "city": "Новосибирск",
                "postal_code": "630000",
                "country": "RU",
                "is_default": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["is_default"] is True

        # Старый address больше не дефолтный
        await db_session.refresh(address)
        assert address.is_default is False

        # У юзера ровно один дефолтный
        defaults = (await db_session.execute(
            select(Address).where(Address.is_default.is_(True))
        )).scalars().all()
        assert len(defaults) == 1

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client):
        response = await client.post(
            "/api/v1/addresses",
            json={
                "address_line1": "X",
                "city": "Y",
                "postal_code": "Z",
                "country": "RU",
            },
        )
        assert response.status_code == 401


class TestListAddresses:
    """GET /addresses."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client, auth_headers):
        response = await client.get("/api/v1/addresses", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_returns_only_my(self, client, auth_headers, address, address_for_admin):
        response = await client.get("/api/v1/addresses", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == address.id

    @pytest.mark.asyncio
    async def test_default_comes_first(self, client, auth_headers, db_session, verified_user):
        """Сначала дефолтный, потом обычные."""
        a1 = Address(
            user_id=verified_user.id,
            address_line1="A1", city="C1", postal_code="111", country="RU",
            is_default=False,
        )
        a2 = Address(
            user_id=verified_user.id,
            address_line1="A2", city="C2", postal_code="222", country="RU",
            is_default=True,
        )
        db_session.add_all([a1, a2])
        await db_session.flush()

        response = await client.get("/api/v1/addresses", headers=auth_headers)
        body = response.json()
        assert body[0]["id"] == a2.id        # дефолтный первым
        assert body[1]["id"] == a1.id


class TestGetAddress:
    """GET /addresses/{id}."""

    @pytest.mark.asyncio
    async def test_get_own(self, client, auth_headers, address):
        response = await client.get(
            f"/api/v1/addresses/{address.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["id"] == address.id

    @pytest.mark.asyncio
    async def test_get_foreign_returns_404(
        self, client, auth_headers, address_for_admin
    ):
        """Чужой адрес — 404, не 403."""
        response = await client.get(
            f"/api/v1/addresses/{address_for_admin.id}", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_missing_returns_404(self, client, auth_headers):
        response = await client.get(
            "/api/v1/addresses/999999", headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateAddress:
    """PATCH /addresses/{id}."""

    @pytest.mark.asyncio
    async def test_patch_own(self, client, auth_headers, address):
        response = await client.patch(
            f"/api/v1/addresses/{address.id}",
            json={"city": "Екатеринбург"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["city"] == "Екатеринбург"
        assert response.json()["address_line1"] == address.address_line1

    @pytest.mark.asyncio
    async def test_patch_to_default_resets_previous(
        self, client, auth_headers, address, db_session, verified_user
    ):
        """PATCH is_default=True снимает флаг с предыдущего дефолтного."""
        a2 = Address(
            user_id=verified_user.id,
            address_line1="A2", city="C2", postal_code="222", country="RU",
            is_default=False,
        )
        db_session.add(a2)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/addresses/{a2.id}",
            json={"is_default": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["is_default"] is True

        await db_session.refresh(address)
        assert address.is_default is False

    @pytest.mark.asyncio
    async def test_patch_foreign_returns_404(
        self, client, auth_headers, address_for_admin
    ):
        response = await client.patch(
            f"/api/v1/addresses/{address_for_admin.id}",
            json={"city": "Hack"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDeleteAddress:
    """DELETE /addresses/{id}."""

    @pytest.mark.asyncio
    async def test_delete_own(self, client, auth_headers, address, db_session):
        response = await client.delete(
            f"/api/v1/addresses/{address.id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Проверяем, что удалён
        found = (await db_session.execute(
            select(Address).where(Address.id == address.id)
        )).scalar_one_or_none()
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_foreign_returns_404(
        self, client, auth_headers, address_for_admin
    ):
        response = await client.delete(
            f"/api/v1/addresses/{address_for_admin.id}", headers=auth_headers
        )
        assert response.status_code == 404


class TestSetDefault:
    """POST /addresses/{id}/set-default."""

    @pytest.mark.asyncio
    async def test_set_default_switches_flag(
        self, client, auth_headers, address, db_session, verified_user
    ):
        a2 = Address(
            user_id=verified_user.id,
            address_line1="A2", city="C2", postal_code="222", country="RU",
            is_default=False,
        )
        db_session.add(a2)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/addresses/{a2.id}/set-default", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["is_default"] is True

        await db_session.refresh(address)
        assert address.is_default is False

    @pytest.mark.asyncio
    async def test_set_default_idempotent(
        self, client, auth_headers, address
    ):
        """Повторный вызов на уже дефолтном — no-op, 200."""
        response = await client.post(
            f"/api/v1/addresses/{address.id}/set-default", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["is_default"] is True

    @pytest.mark.asyncio
    async def test_set_default_foreign_returns_404(
        self, client, auth_headers, address_for_admin
    ):
        response = await client.post(
            f"/api/v1/addresses/{address_for_admin.id}/set-default",
            headers=auth_headers,
        )
        assert response.status_code == 404