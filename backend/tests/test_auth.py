# tests/test_auth.py
"""
Тесты аутентификации: register / login / refresh / logout / verify-email / resend.

Ядро доказательств:
- login-oracle: одинаковый 401 на неизвестный email и неверный пароль.
- reuse-detection: revoked refresh → 401 + вся семья revoked в БД.
- инвариант верификации: status и is_email_verified меняются вместе.
- resend инвалидирует старые pending-токены.
"""
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, hash_refresh_token
from app.db.enum import UserRole, UserStatus
from app.models.email_verification import EmailVerification
from app.models.refresh_token import RefreshToken
from app.models.user import User as UserModel

REGISTER_PAYLOAD = {
    "email": "new@example.com",
    "password": "strong-password-1234",
    "first_name": "New",
    "last_name": "User",
    "phone_number": "+79995550001",
}


# ============================================================
#  Register
# ============================================================

class TestRegister:
    @pytest.mark.asyncio
    async def test_register_creates_pending_unverified_user(self, client, db_session):
        response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["status"] == "pending"
        assert body["is_email_verified"] is False
        assert "password_hash" not in body  # не утекло

        # ✅ В БД создан EmailVerification
        user = (await db_session.execute(
            select(UserModel).where(UserModel.email == "new@example.com")
        )).scalar_one()
        verification = (await db_session.execute(
            select(EmailVerification).where(EmailVerification.user_id == user.id)
        )).scalar_one()
        assert verification.verified_at is None
        assert verification.expires_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client, verified_user):
        payload = {**REGISTER_PAYLOAD, "email": verified_user.email}
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_rejects_extra_fields(self, client):
        payload = {**REGISTER_PAYLOAD, "is_admin": True}
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422


# ============================================================
#  Login
# ============================================================

class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success_sets_refresh_cookie(self, client, verified_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "test-password-1234",
        })
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

        # ✅ refresh — в httpOnly-cookie
        s = get_settings()
        assert s.REFRESH_COOKIE_NAME in response.cookies
        # httpx не отдаёт httpOnly-флаг в response.cookies, но Set-Cookie содержит его
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "httponly" in set_cookie_header.lower()
        assert f"path={s.REFRESH_COOKIE_PATH.lower()}" in set_cookie_header.lower()

    @pytest.mark.asyncio
    async def test_login_wrong_password_401(self, client, verified_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "wrong-password",
        })
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_same_401(self, client, verified_user):
        """
        ✅ Login-oracle off: неизвестный email → тот же detail, что и неверный пароль.
        Не даём атакующему различить 'email не зарегистрирован' vs 'неверный пароль'.
        """
        r_unknown = await client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "any-password-1234",
        })
        r_wrong = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "wrong-password-1234",
        })

        assert r_unknown.status_code == 401
        assert r_wrong.status_code == 401
        assert r_unknown.json()["detail"] == r_wrong.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_unverified_403(self, client, db_session):
        # Создаём PENDING-юзера
        user = UserModel(
            email="pending@example.com",
            password_hash=hash_password("pending-password-1234"),
            first_name="P", last_name="U", phone_number="+79990000005",
            role=UserRole.CUSTOMER,
            status=UserStatus.PENDING,
            is_email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        response = await client.post("/api/v1/auth/login", json={
            "email": "pending@example.com",
            "password": "pending-password-1234",
        })
        assert response.status_code == 403
        assert "not verified" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_banned_403(self, client, banned_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": banned_user.email,
            "password": "banned-password-1234",
        })
        assert response.status_code == 403
        assert "banned" in response.json()["detail"].lower()


# ============================================================
#  Verify-email / resend
# ============================================================

class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_verify_flips_both_flags_atomically(self, client, db_session):
        """
        ✅ Инвариант: status и is_email_verified меняются вместе, в одной транзакции.
        """
        user = UserModel(
            email="verify@example.com",
            password_hash=hash_password("verify-password-1234"),
            first_name="V", last_name="U", phone_number="+79990000006",
            role=UserRole.CUSTOMER,
            status=UserStatus.PENDING,
            is_email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        verification = EmailVerification(
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(verification)
        await db_session.flush()
        token = str(verification.token)

        response = await client.get(f"/api/v1/auth/verify-email?token={token}")
        assert response.status_code == 200

        await db_session.refresh(user)
        assert user.status == UserStatus.ACTIVE
        assert user.is_email_verified is True

    @pytest.mark.asyncio
    async def test_verify_expired_400(self, client, db_session):
        user = UserModel(
            email="expired@example.com",
            password_hash=hash_password("x-password-1234"),
            first_name="E", last_name="U", phone_number="+79990000007",
            role=UserRole.CUSTOMER, status=UserStatus.PENDING, is_email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        verification = EmailVerification(
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(verification)
        await db_session.flush()

        response = await client.get(f"/api/v1/auth/verify-email?token={verification.token}")
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_verify_unknown_token_400(self, client):
        response = await client.get(f"/api/v1/auth/verify-email?token={uuid.uuid4()}")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_resend_invalidates_old_token(self, client, db_session):
        """
        ✅ После resend старый pending-токен больше не работает.
        """
        user = UserModel(
            email="resend@example.com",
            password_hash=hash_password("resend-password-1234"),
            first_name="R", last_name="U", phone_number="+79990000008",
            role=UserRole.CUSTOMER, status=UserStatus.PENDING, is_email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        old = EmailVerification(
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        db_session.add(old)
        await db_session.flush()
        old_token = str(old.token)

        # resend
        r = await client.post("/api/v1/auth/resend-verification", json={
            "email": "resend@example.com",
        })
        assert r.status_code == 200

        # Старый токен мёртв
        r_old = await client.get(f"/api/v1/auth/verify-email?token={old_token}")
        assert r_old.status_code == 400

    @pytest.mark.asyncio
    async def test_resend_unknown_email_returns_200(self, client):
        """
        ✅ Email-oracle off: для неизвестного email — тот же 200 с нейтральным текстом.
        """
        r = await client.post("/api/v1/auth/resend-verification", json={
            "email": "nobody@example.com",
        })
        assert r.status_code == 200
        assert "if the address is registered" in r.json()["message"].lower()


# ============================================================
#  /me
# ============================================================

class TestMe:
    @pytest.mark.asyncio
    async def test_me_returns_current_user(self, client, verified_user, auth_headers):
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == verified_user.email
        assert body["public_id"] == str(verified_user.public_id)

    @pytest.mark.asyncio
    async def test_me_without_token_401(self, client):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401


# ============================================================
#  Refresh: ротация + reuse-detection
# ============================================================

class TestRefreshRotation:
    @pytest.mark.asyncio
    async def test_refresh_rotates_token(self, client, verified_user, db_session):
        """
        ✅ Ротация: старый revoked, новый активен, family_id сохраняется.
        """
        # login
        login = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "test-password-1234",
        })
        assert login.status_code == 200
        s = get_settings()
        old_raw = login.cookies[s.REFRESH_COOKIE_NAME]
        old_hash = hash_refresh_token(old_raw)

        # refresh
        refresh = await client.post("/api/v1/auth/refresh")
        assert refresh.status_code == 200
        new_raw = refresh.cookies[s.REFRESH_COOKIE_NAME]
        assert new_raw != old_raw

        # Проверяем БД
        old_record = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == old_hash)
        )).scalar_one()
        new_hash = hash_refresh_token(new_raw)
        new_record = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == new_hash)
        )).scalar_one()

        assert old_record.revoked is True
        assert old_record.revoked_at is not None
        assert new_record.revoked is False
        assert new_record.family_id == old_record.family_id   # ✅ та же семья

    @pytest.mark.asyncio
    async def test_refresh_rotation_revokes_old_token(
        self, client, verified_user, db_session
    ):
        """
        ✅ Ротация: старый refresh revoked сразу после refresh.

        Проверка savepoint-совместима (обе сессии внутри T1).

        Полная проверка reuse-detection (401 + отзыв всей семьи) —
        в tests/test_auth_integration.py::test_refresh_reuse_detection_persists_after_401.
        Причина: savepoint-изоляция не видит commits из отдельных сессий,
        которые использует revoke_family_independently.
        """
        from app.core.security import hash_refresh_token

        s = get_settings()

        login = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "test-password-1234",
        })
        assert login.status_code == 200
        refresh_1_raw = login.cookies[s.REFRESH_COOKIE_NAME]
        refresh_1_hash = hash_refresh_token(refresh_1_raw)

        # Ротация 1 → 2
        r2 = await client.post("/api/v1/auth/refresh")
        assert r2.status_code == 200

        # ✅ Проверяем: старый revoked, новый активен, семья сохранена
        old_record = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == refresh_1_hash)
        )).scalar_one()
        assert old_record.revoked is True
        assert old_record.revoked_at is not None

        new_raw = r2.cookies[s.REFRESH_COOKIE_NAME]
        assert new_raw != refresh_1_raw
        new_hash = hash_refresh_token(new_raw)
        new_record = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == new_hash)
        )).scalar_one()
        assert new_record.revoked is False
        assert new_record.family_id == old_record.family_id


    @pytest.mark.asyncio
    async def test_refresh_after_logout_401(self, client, verified_user):
        """✅ Logout отзывает семью → refresh не работает."""
        s = get_settings()

        login = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "test-password-1234",
        })
        raw = login.cookies[s.REFRESH_COOKIE_NAME]

        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200

        # logout очистил cookie в jar; вернём старый raw руками
        client.cookies.set(
            s.REFRESH_COOKIE_NAME,
            raw,
            path=s.REFRESH_COOKIE_PATH,
        )

        refresh = await client.post("/api/v1/auth/refresh")
        assert refresh.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_produces_fresh_iat_and_unique_jti(
        self, client, verified_user, db_session
    ):
        """
        ✅ JWT payload проверяется напрямую:
        - iat после refresh свежее, чем в исходном login;
        - jti уникален на каждую выдачу (не переиспользуется).
        """
        import jwt

        s = get_settings()

        # Login → token_1
        login = await client.post("/api/v1/auth/login", json={
            "email": verified_user.email,
            "password": "test-password-1234",
        })
        assert login.status_code == 200
        token_1 = login.json()["access_token"]
        payload_1 = jwt.decode(
            token_1, s.SECRET_KEY.get_secret_value(),
            algorithms=[s.ALGORITHM], options={"require": ["iat", "jti"]},
        )

        # Ждём гарантированно >1 секунды, чтобы iat отличался (unix timestamp)
        import time
        time.sleep(1.1)

        # Refresh → token_2
        refresh = await client.post("/api/v1/auth/refresh")
        assert refresh.status_code == 200
        token_2 = refresh.json()["access_token"]
        payload_2 = jwt.decode(
            token_2, s.SECRET_KEY.get_secret_value(),
            algorithms=[s.ALGORITHM], options={"require": ["iat", "jti"]},
        )

        # ✅ iat стал свежее
        assert payload_2["iat"] > payload_1["iat"], (
            f"iat не обновился: {payload_1['iat']} vs {payload_2['iat']}"
        )
        # ✅ jti уникален
        assert payload_2["jti"] != payload_1["jti"], (
            f"jti не уникален: {payload_1['jti']}"
        )

# ============================================================
#  Ban-политика на access-токене
# ============================================================

class TestBanPolicyOnAccess:
    @pytest.mark.asyncio
    async def test_banned_user_access_403(self, client, banned_headers):
        """✅ Даже с валидным access-токеном banned → 403."""
        response = await client.get("/api/v1/auth/me", headers=banned_headers)
        assert response.status_code == 403
        assert "banned" in response.json()["detail"].lower()


# ============================================================
#  Expired access
# ============================================================

class TestExpiredAccess:
    @pytest.mark.asyncio
    async def test_expired_access_401_with_detail(self, client, verified_user):
        """✅ Протухший access → 401 + корректный detail."""
        s = get_settings()
        now = datetime.now(UTC)
        expired_token = jwt.encode(
            {
                "sub": str(verified_user.public_id),
                "type": "access",
                "iat": now - timedelta(hours=2),
                "exp": now - timedelta(hours=1),
                "jti": uuid.uuid4().hex,
            },
            s.SECRET_KEY.get_secret_value(),
            algorithm=s.ALGORITHM,
        )
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()


# ============================================================
#  require_roles на товарах
# ============================================================

class TestRequireRoles:
    @pytest.mark.asyncio
    async def test_customer_cannot_create_product(self, client, category, auth_headers):
        """✅ CUSTOMER → 403."""
        payload = {
            "name": "Restricted",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post("/api/v1/products", json=payload, headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_create_product(self, client, category, admin_headers):
        payload = {
            "name": "Admin Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post("/api/v1/products", json=payload, headers=admin_headers)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_seller_can_create_product(self, client, category, seller_headers):
        payload = {
            "name": "Seller Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post("/api/v1/products", json=payload, headers=seller_headers)
        assert response.status_code == 201

        
    @pytest.mark.asyncio
    async def test_moderator_can_create_product(self, client, category, db_session):
        """
        ✅ MODERATOR тоже входит в _WRITE_ROLES.

        Список ролей для write-операций каталога:
        ADMIN, MODERATOR, SELLER. Проверяем все три (см. соседние тесты).
        """
        from app.core.security import hash_password
        from app.db.enum import UserRole, UserStatus
        from app.models.user import User as UserModel

        user = UserModel(
            email="moderator@example.com",
            password_hash=hash_password("moderator-password-1234"),
            first_name="Moderator", last_name="User",
            phone_number="+79990000099",
            role=UserRole.MODERATOR,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        headers = {
            "Authorization": f"Bearer {create_access_token(str(user.public_id))}"
        }

        payload = {
            "name": "Moderator Product",
            "description": "Test",
            "cost": "100.00",
            "category_id": category.id,
        }
        response = await client.post(
            "/api/v1/products", json=payload, headers=headers
        )
        assert response.status_code == 201

# tests/test_auth.py
class TestInvalidTokenNeutralDetail:
    """✅ SEC-002: детали pyjwt не утекают клиенту."""

    @pytest.mark.asyncio
    async def test_invalid_token_neutral_detail(self, client, verified_user):
        """Битый токен → 401 с нейтральным detail, без pyjwt-текста."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert response.status_code == 401
        detail = response.json()["detail"].lower()
        # Нейтральное сообщение
        assert "invalid access token" in detail
        # Не утекли внутренности pyjwt
        assert "not enough segments" not in detail
        assert "signature" not in detail
        assert "decode" not in detail
        assert "padding" not in detail

    @pytest.mark.asyncio
    async def test_expired_token_still_says_expired(self, client, verified_user):
        """Просроченный токен → detail 'expired' (не утекает, но полезно)."""
        import uuid
        from datetime import datetime, timedelta

        import jwt

        from app.core.config import get_settings

        s = get_settings()
        now = datetime.now(UTC)
        expired = jwt.encode(
            {
                "sub": str(verified_user.public_id),
                "type": "access",
                "iat": now - timedelta(hours=2),
                "exp": now - timedelta(hours=1),
                "jti": uuid.uuid4().hex,
            },
            s.SECRET_KEY.get_secret_value(),
            algorithm=s.ALGORITHM,
        )
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()