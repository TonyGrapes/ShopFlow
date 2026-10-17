"""
Сервисные тесты refund_service.

Проверяют:
- create_refund: happy, идемпотентность, валидации (payment not completed,
  amount > remaining, invalid reason, external_id conflict);
- частичный возврат → payment остаётся completed;
- полный возврат → payment.status = refunded;
- state machine: pending → completed/failed, терминальные — ошибка;
- get_refund_by_public_id, list_refunds_for_payment.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from app.db.enum import PaymentStatus, RefundStatus
from app.models.payment import Payment
from app.models.refund import Refund
from app.schemas.refund import RefundCreate
from app.services import refund_service
from app.services.refund_service import validate_refund_transition
from fastapi import HTTPException
from sqlalchemy import select

# ============================================================
#  create_refund — happy path
# ============================================================

class TestCreateRefundHappy:
    """Успешное создание возврата."""

    @pytest.mark.asyncio
    async def test_partial_refund(self, db_session, payment_for_refund):
        """Частичный возврат: 300 из 1000. Payment остаётся completed."""
        data = RefundCreate(
            amount=Decimal("300.00"),
            reason="customer_request",
            external_id="refund-happy-1",
        )
        refund = await refund_service.create_refund(
            db_session, payment_for_refund, data
        )

        assert refund.id is not None
        assert refund.public_id is not None
        assert refund.amount == Decimal("300.00")
        assert refund.status == RefundStatus.COMPLETED
        assert refund.refunded_at is not None
        assert refund.reason == "customer_request"

        # Payment остаётся completed — возврат частичный
        await db_session.refresh(payment_for_refund)
        assert payment_for_refund.status == PaymentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_full_refund_flips_payment_status(
        self, db_session, payment_for_refund
    ):
        """Полный возврат 1000/1000 → payment.status = refunded."""
        data = RefundCreate(
            amount=Decimal("1000.00"),
            reason="defective",
            external_id="refund-full-1",
        )
        refund = await refund_service.create_refund(
            db_session, payment_for_refund, data
        )
        assert refund.amount == Decimal("1000.00")

        await db_session.refresh(payment_for_refund)
        assert payment_for_refund.status == PaymentStatus.REFUNDED

    @pytest.mark.asyncio
    async def test_two_partial_refunds_sum_to_full(
        self, db_session, payment_for_refund
    ):
        """Два частичных возврата (400 + 600 = 1000) → payment refunded."""
        await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("400.00"), external_id="r-1"),
        )
        await db_session.refresh(payment_for_refund)
        assert payment_for_refund.status == PaymentStatus.COMPLETED

        await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("600.00"), external_id="r-2"),
        )
        await db_session.refresh(payment_for_refund)
        assert payment_for_refund.status == PaymentStatus.REFUNDED

    @pytest.mark.asyncio
    async def test_refund_without_external_id(self, db_session, payment_for_refund):
        """external_id=None — каждый вызов создаёт новый Refund."""
        r1 = await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("100.00")),
        )
        r2 = await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("100.00")),
        )
        assert r1.id != r2.id
        assert r1.external_id is None
        assert r2.external_id is None


# ============================================================
#  create_refund — валидации
# ============================================================

class TestCreateRefundValidation:
    """Валидация входа."""

    @pytest.mark.asyncio
    async def test_external_id_replay_returns_existing(
        self, db_session, payment_for_refund
    ):
        """Replay того же external_id → тот же Refund."""
        data = RefundCreate(
            amount=Decimal("300.00"),
            external_id="replay-key",
        )
        r1 = await refund_service.create_refund(
            db_session, payment_for_refund, data
        )
        r2 = await refund_service.create_refund(
            db_session, payment_for_refund, data
        )
        assert r1.id == r2.id
        assert r1.public_id == r2.public_id

        # В БД только один Refund
        rows = (await db_session.execute(
            select(Refund).where(Refund.external_id == "replay-key")
        )).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_external_id_other_payment_409(
        self, db_session, payment_for_refund, admin_user, address, product
    ):
        """external_id занят другим платежом → 409."""
        from app.models.order import Order
        from app.models.order_item import OrderItem
        from app.db.enum import OrderStatus

        # Второй заказ + платёж
        o2 = Order(
            user_id=admin_user.id, total=Decimal("1000.00"),
            status=OrderStatus.PAID,
            shipping_address_id=address.id,
        )
        db_session.add(o2)
        await db_session.flush()
        db_session.add(OrderItem(
            order_id=o2.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await db_session.flush()
        p2 = Payment(
            order_id=o2.id, amount=Decimal("1000.00"),
            currency="RUB", payment_method="card",
            status=PaymentStatus.COMPLETED,
            external_id="test-payment-refund-2",
            paid_at=datetime.now(timezone.utc),
        )
        db_session.add(p2)
        await db_session.flush()
        await db_session.refresh(p2)

        # Возврат на первый
        await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("300.00"), external_id="shared-ext"),
        )

        # Возврат на второй с тем же external_id → 409
        with pytest.raises(HTTPException) as exc:
            await refund_service.create_refund(
                db_session, p2,
                RefundCreate(amount=Decimal("100.00"), external_id="shared-ext"),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "external_id_taken"

    @pytest.mark.asyncio
    async def test_payment_not_completed_422(
        self, db_session, payment_for_refund
    ):
        """Payment в pending → 422."""
        payment_for_refund.status = PaymentStatus.PENDING
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await refund_service.create_refund(
                db_session, payment_for_refund,
                RefundCreate(amount=Decimal("100.00")),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "payment_not_refundable"

    @pytest.mark.asyncio
    async def test_invalid_reason_422(
        self, db_session, payment_for_refund
    ):
        """Reason вне списка → 422."""
        with pytest.raises(HTTPException) as exc:
            await refund_service.create_refund(
                db_session, payment_for_refund,
                RefundCreate(amount=Decimal("100.00"), reason="hacked"),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "invalid_refund_reason"
        assert "hacked" in exc.value.detail["reason"]

    @pytest.mark.asyncio
    async def test_amount_exceeds_remaining_422(
        self, db_session, payment_for_refund
    ):
        """amount > payment.amount - already_refunded → 422."""
        # Уже вернули 800
        await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("800.00"), external_id="r-first"),
        )
        await db_session.refresh(payment_for_refund)

        # Пробуем вернуть 300 (осталось только 200)
        with pytest.raises(HTTPException) as exc:
            await refund_service.create_refund(
                db_session, payment_for_refund,
                RefundCreate(amount=Decimal("300.00"), external_id="r-second"),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "amount_exceeds_remaining"
        assert exc.value.detail["max_refundable"] == "200.00"
        assert exc.value.detail["already_refunded"] == "800.00"

    @pytest.mark.asyncio
    async def test_amount_equal_to_remaining_ok(
        self, db_session, payment_for_refund
    ):
        """amount == remaining — допустимо."""
        await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("800.00"), external_id="r-first"),
        )
        await db_session.refresh(payment_for_refund)

        refund = await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("200.00"), external_id="r-second"),
        )
        assert refund.amount == Decimal("200.00")

        await db_session.refresh(payment_for_refund)
        assert payment_for_refund.status == PaymentStatus.REFUNDED


# ============================================================
#  State machine
# ============================================================

class TestRefundStateMachine:
    """validate_refund_transition."""

    @pytest.mark.parametrize("current,new,should_pass", [
        (RefundStatus.PENDING, RefundStatus.COMPLETED, True),
        (RefundStatus.PENDING, RefundStatus.FAILED, True),
        (RefundStatus.COMPLETED, RefundStatus.FAILED, False),
        (RefundStatus.COMPLETED, RefundStatus.PENDING, False),
        (RefundStatus.FAILED, RefundStatus.COMPLETED, False),
        (RefundStatus.FAILED, RefundStatus.PENDING, False),
    ])
    def test_transitions(self, current, new, should_pass):
        if should_pass:
            validate_refund_transition(current, new)
        else:
            with pytest.raises(HTTPException) as exc:
                validate_refund_transition(current, new)
            assert exc.value.status_code == 422
            assert exc.value.detail["code"] == "invalid_refund_transition"


# ============================================================
#  Чтение
# ============================================================

class TestReadRefunds:
    """get_refund_by_public_id, list_refunds_for_payment."""

    @pytest.mark.asyncio
    async def test_get_by_public_id(
        self, db_session, completed_refund: Refund
    ):
        found = await refund_service.get_refund_by_public_id(
            db_session, completed_refund.public_id
        )
        assert found is not None
        assert found.id == completed_refund.id

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, db_session):
        found = await refund_service.get_refund_by_public_id(
            db_session, "00000000-0000-0000-0000-000000000000"
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_list_for_payment(
        self, db_session, payment_for_refund, completed_refund
    ):
        """Возвраты по платежу — список. completed_refund уже есть."""
        # Добавляем второй
        await refund_service.create_refund(
            db_session, payment_for_refund,
            RefundCreate(amount=Decimal("200.00"), external_id="r-second"),
        )

        refunds = await refund_service.list_refunds_for_payment(
            db_session, payment_for_refund.id
        )
        assert len(refunds) == 2
        amounts = {r.amount for r in refunds}
        assert amounts == {Decimal("300.00"), Decimal("200.00")}

    @pytest.mark.asyncio
    async def test_list_empty(self, db_session, payment_for_refund):
        refunds = await refund_service.list_refunds_for_payment(
            db_session, payment_for_refund.id
        )
        assert refunds == []