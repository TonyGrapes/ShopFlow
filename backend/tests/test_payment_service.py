# tests/test_payment_service.py
"""
Тесты payment_service: идемпотентность, проверки статуса order.
"""
from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError, ValidationError
from app.db.enum import OrderStatus, PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.services import order_service, payment_service
from fastapi import HTTPException
from sqlalchemy import select


class TestProcessPaymentHappy:
    """Успешная оплата."""

    @pytest.mark.asyncio
    async def test_pay_pending_order(self, db_session, order):
        payment = await payment_service.process_payment(
            db=db_session,
            order=order,
            external_id="ext-1",
            method=PaymentMethod.CARD,
        )
        assert payment.id is not None
        assert payment.external_id == "ext-1"
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.amount == order.total
        assert payment.paid_at is not None

        # order перешёл в paid
        assert order.status == OrderStatus.PAID


class TestProcessPaymentIdempotency:
    """Replay того же external_id."""

    @pytest.mark.asyncio
    async def test_same_external_id_same_order_returns_existing(
        self, db_session, order
    ):
        """Повторный вызов с тем же external_id возвращает тот же Payment."""
        p1 = await payment_service.process_payment(
            db=db_session, order=order,
            external_id="ext-2", method=PaymentMethod.CARD,
        )
        p2 = await payment_service.process_payment(
            db=db_session, order=order,
            external_id="ext-2", method=PaymentMethod.CARD,
        )
        assert p1.id == p2.id
        assert p1.public_id == p2.public_id

        # Только один Payment в БД
        payments = (await db_session.execute(
            select(Payment).where(Payment.external_id == "ext-2")
        )).scalars().all()
        assert len(payments) == 1

    @pytest.mark.asyncio
    async def test_same_external_id_different_order_409(
        self, db_session, order, address, admin_user, product
    ):
        """external_id занят другим заказом → 409."""
        from app.models.order import Order as OrderModel

        # Создаём второй заказ (принадлежит admin_user)
        other_order = OrderModel(
            user_id=admin_user.id,
            total=Decimal("500.00"),
            status=OrderStatus.PENDING,
            shipping_address_id=address.id,   # address verified_user — не важно для теста
        )
        db_session.add(other_order)
        await db_session.flush()

        # Платим первый заказ с external_id
        await payment_service.process_payment(
            db=db_session, order=order,
            external_id="ext-shared", method=PaymentMethod.CARD,
        )

        # Платим второй заказ с тем же external_id → 409
        with pytest.raises(ConflictError) as exc:
            await payment_service.process_payment(
                db=db_session, order=other_order,
                external_id="ext-shared", method=PaymentMethod.CARD,
            )
        assert exc.value.status_code == 409
        assert exc.value.code == "external_id_taken"


class TestProcessPaymentStateChecks:
    """Проверки статуса order."""

    @pytest.mark.asyncio
    async def test_canceled_order_422(self, db_session, order):
        order.status = OrderStatus.CANCELED
        await db_session.flush()

        with pytest.raises(ValidationError) as exc:
            await payment_service.process_payment(
                db=db_session, order=order,
                external_id="ext-canceled", method=PaymentMethod.CARD,
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "order_canceled"

    @pytest.mark.asyncio
    async def test_delivered_order_422(self, db_session, order):
        order.status = OrderStatus.DELIVERED
        await db_session.flush()

        with pytest.raises(ValidationError) as exc:
            await payment_service.process_payment(
                db=db_session, order=order,
                external_id="ext-delivered", method=PaymentMethod.CARD,
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "order_not_payable"

    @pytest.mark.asyncio
    async def test_no_external_id_creates_new_payment(
        self, db_session, order
    ):
        """Без external_id — каждый вызов создаёт новый Payment."""
        p1 = await payment_service.process_payment(
            db=db_session, order=order,
            external_id=None, method=PaymentMethod.CARD,
        )
        assert p1.external_id is None
        assert p1.status == PaymentStatus.COMPLETED