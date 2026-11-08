"""Тесты /api/v1/admin/users."""
import pytest
from sqlalchemy import select

from app.models.refresh_token import RefreshToken
from app.models.user import User as UserModel


class TestAdminUsersList:
    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        response = await client.get("/api/v1/admin/users")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_customer_403(self, client, auth_headers):
        response = await client.get("/api/v1/admin/users", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_admin_ok(
        self, client, admin_headers, verified_user, admin_user
    ):
        response = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2

    @pytest.mark.asyncio
    async def test_filter_by_role(
        self, client, admin_headers, verified_user, admin_user
    ):
        response = await client.get(
            "/api/v1/admin/users?role=admin", headers=admin_headers,
        )
        body = response.json()
        assert all(i["role"] == "admin" for i in body["items"])


class TestAdminUsersRoleChange:
    @pytest.mark.asyncio
    async def test_change_role_ok(
        self, client, admin_headers, verified_user
    ):
        response = await client.patch(
            f"/api/v1/admin/users/{verified_user.public_id}/role",
            json={"role": "moderator"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["role"] == "moderator"

    @pytest.mark.asyncio
    async def test_change_role_requires_admin(
        self, client, db_session, verified_user
    ):
        """MODERATOR не может менять роль."""
        from app.core.security import create_access_token, hash_password
        from app.db.enum import UserRole, UserStatus

        mod = UserModel(
            email="mod3@example.com",
            password_hash=hash_password("mod-password-3"),
            first_name="M", last_name="U", phone_number="+79990000052",
            role=UserRole.MODERATOR, status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        db_session.add(mod)
        await db_session.flush()
        await db_session.refresh(mod)

        headers = {"Authorization": f"Bearer {create_access_token(str(mod.public_id))}"}
        response = await client.patch(
            f"/api/v1/admin/users/{verified_user.public_id}/role",
            json={"role": "admin"},
            headers=headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_change_own_role(
        self, client, admin_headers, admin_user
    ):
        response = await client.patch(
            f"/api/v1/admin/users/{admin_user.public_id}/role",
            json={"role": "customer"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "cannot_modify_self"

    @pytest.mark.asyncio
    async def test_change_role_revokes_refresh(
        self, client, admin_headers, verified_user, db_session
    ):
        # Создаём refresh для verified_user вручную
        from datetime import UTC, datetime, timedelta

        from app.core.security import hash_refresh_token

        db_session.add(RefreshToken(
            user_id=verified_user.id,
            token_hash=hash_refresh_token("seed"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            revoked=False,
        ))
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/admin/users/{verified_user.public_id}/role",
            json={"role": "moderator"},
            headers=admin_headers,
        )
        assert response.status_code == 200

        tokens = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == verified_user.id)
        )).scalars().all()
        assert all(t.revoked for t in tokens)


class TestAdminUsersStatusChange:
    @pytest.mark.asyncio
    async def test_ban_and_revoke(
        self, client, admin_headers, verified_user, db_session
    ):
        from datetime import UTC, datetime, timedelta

        from app.core.security import hash_refresh_token

        db_session.add(RefreshToken(
            user_id=verified_user.id,
            token_hash=hash_refresh_token("seed-ban"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            revoked=False,
        ))
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/admin/users/{verified_user.public_id}/status",
            json={"status": "banned"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "banned"

        tokens = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == verified_user.id)
        )).scalars().all()
        assert all(t.revoked for t in tokens)

    @pytest.mark.asyncio
    async def test_cannot_ban_self(
        self, client, admin_headers, admin_user
    ):
        response = await client.patch(
            f"/api/v1/admin/users/{admin_user.public_id}/status",
            json={"status": "banned"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "cannot_modify_self"

    @pytest.mark.asyncio
    async def test_unban_ok(
        self, client, admin_headers, banned_user
    ):
        response = await client.patch(
            f"/api/v1/admin/users/{banned_user.public_id}/status",
            json={"status": "active"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_missing_user_404(
        self, client, admin_headers
    ):
        response = await client.patch(
            "/api/v1/admin/users/00000000-0000-0000-0000-000000000000/status",
            json={"status": "banned"},
            headers=admin_headers,
        )
        assert response.status_code == 404