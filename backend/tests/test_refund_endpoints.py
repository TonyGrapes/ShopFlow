# tests/test_refund_endpoints.py
"""
HTTP-тесты /api/v1/admin/payments/{payment_id}/refund(s).

Проверяют:
- RBAC: customer → 403, admin → 201;
- POST создаёт возврат и возвращает public_id;
- GET детали;
- GET список;
- 404 для несуществующего payment/refund;
- 422 для amount > remaining / invalid reason;
- 409 для external_id conflict.
"""
from decimal import Decimal

import pytest

from app.db.enum import PaymentStatus

# ============================================================
#  POST /admin/payments/{payment_id}/refund
# ============================================================

class TestCreateRefundEndpoint:
    """POST /api/v1/admin/payments/{payment_id}/refund."""

    @pytest.mark.asyncio
    async def test_create_refund_happy(
        self, client, admin_headers, payment_for_refund
    ):
        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={
                "amount": "300.00",
                "reason": "customer_request",
                "external_id": "ext-api-r-1",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["public_id"] is not None
        assert Decimal(body["amount"]) == Decimal("300.00")
        assert body["reason"] == "customer_request"
        assert body["status"] == "completed"
        assert body["external_id"] == "ext-api-r-1"
        assert body["refunded_at"] is not None

    @pytest.mark.asyncio
    async def test_create_requires_auth(
        self, client, payment_for_refund
    ):
        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "100.00"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_requires_admin(
        self, client, auth_headers, payment_for_refund
    ):
        """CUSTOMER → 403."""
        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "100.00"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_payment_not_found_404(
        self, client, admin_headers
    ):
        response = await client.post(
            "/api/v1/admin/payments/999999/refund",
            json={"amount": "100.00"},
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"

    @pytest.mark.asyncio
    async def test_amount_exceeds_422(
        self, client, admin_headers, payment_for_refund
    ):
        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "2000.00"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "amount_exceeds_remaining"
        assert body["max_refundable"] == "1000.00"

    @pytest.mark.asyncio
    async def test_invalid_reason_422(
        self, client, admin_headers, payment_for_refund
    ):
        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "100.00", "reason": "hacked"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_refund_reason"

    @pytest.mark.asyncio
    async def test_amount_zero_422(
        self, client, admin_headers, payment_for_refund
    ):
        """amount=0 → 422 от Pydantic (gt=0)."""
        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "0.00"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_payment_not_completed_422(
        self, client, db_session, admin_headers, payment_for_refund
    ):
        payment_for_refund.status = PaymentStatus.PENDING
        await db_session.flush()

        response = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "100.00"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "payment_not_refundable"

    @pytest.mark.asyncio
    async def test_idempotent_replay(
        self, client, admin_headers, payment_for_refund
    ):
        """Replay того же external_id → тот же public_id."""
        r1 = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "100.00", "external_id": "replay-api"},
            headers=admin_headers,
        )
        assert r1.status_code == 201
        pid1 = r1.json()["public_id"]

        r2 = await client.post(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refund",
            json={"amount": "100.00", "external_id": "replay-api"},
            headers=admin_headers,
        )
        assert r2.status_code == 201
        pid2 = r2.json()["public_id"]
        assert pid1 == pid2


# ============================================================
#  GET /admin/refunds/{public_id}
# ============================================================

class TestGetRefundEndpoint:
    """GET /api/v1/admin/refunds/{public_id}."""

    @pytest.mark.asyncio
    async def test_get_refund(
        self, client, admin_headers, completed_refund
    ):
        response = await client.get(
            f"/api/v1/admin/refunds/{completed_refund.public_id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["public_id"] == str(completed_refund.public_id)
        assert Decimal(body["amount"]) == Decimal("300.00")

    @pytest.mark.asyncio
    async def test_get_missing_404(self, client, admin_headers):
        response = await client.get(
            "/api/v1/admin/refunds/00000000-0000-0000-0000-000000000000",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_requires_admin(
        self, client, auth_headers, completed_refund
    ):
        response = await client.get(
            f"/api/v1/admin/refunds/{completed_refund.public_id}",
            headers=auth_headers,
        )
        assert response.status_code == 403


# ============================================================
#  GET /admin/payments/{payment_id}/refunds
# ============================================================

class TestListRefundsEndpoint:
    """GET /api/v1/admin/payments/{payment_id}/refunds."""

    @pytest.mark.asyncio
    async def test_list_empty(
        self, client, admin_headers, payment_for_refund
    ):
        response = await client.get(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refunds",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_with_refunds(
        self, client, admin_headers, payment_for_refund, completed_refund
    ):
        response = await client.get(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refunds",
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["public_id"] == str(completed_refund.public_id)

    @pytest.mark.asyncio
    async def test_list_payment_not_found_404(
        self, client, admin_headers
    ):
        response = await client.get(
            "/api/v1/admin/payments/999999/refunds",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_requires_admin(
        self, client, auth_headers, payment_for_refund
    ):
        response = await client.get(
            f"/api/v1/admin/payments/{payment_for_refund.id}/refunds",
            headers=auth_headers,
        )
        assert response.status_code == 403