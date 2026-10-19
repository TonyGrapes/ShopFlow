# app/services/payment_service.py
"""
Сервис платежей (mock).

Контракт:
- Idempotent by external_id: повторный POST с тем же external_id
  возвращает существующий Payment (200), а не создаёт дубль.
- Семантика webhook: если платёжный шлюз повторит webhook — мы
  не спишем дважды.
- Mock-платёж: Payment создаётся сразу со status=completed,
  order.status → paid. Реальная интеграция сделает Payment pending
  и подтвердит его через /webhooks/payment.

Согласовано на ревью Эпика 5:
- external_id занят другим order → 409
- external_id занят этим order → 200 (idempotent replay)
- order уже paid → 409
- order canceled/shipped/delivered → 422
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.db.enum import OrderStatus, PaymentMethod, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment
from app.schemas.payment import PaymentResponse

logger = logging.getLogger(__name__)

_PAYMENT_EXTERNAL_ID_CONSTRAINT = "idx_payments_external_id"

async def process_payment(
    db: AsyncSession,
    order: Order,
    external_id: str | None,
    method: PaymentMethod,
) -> Payment:
    """
    Обрабатывает платёж. Идемпотентно по external_id.

    Порядок проверок:
    1. external_id уже привязан к ЭТОМУ order → 200 replay.
    2. external_id привязан к ДРУГОМУ order → 409.
    3. order canceled → 422.
    4. order не в pending → 422.
    5. Иначе — создать Payment.
    """
    # ============================================================
    #  1-2. Idempotency по external_id — приоритетнее статуса
    # ============================================================
    if external_id is not None:
        existing = (await db.execute(
            select(Payment).where(Payment.external_id == external_id)
        )).scalar_one_or_none()

        if existing is not None:
            if existing.order_id == order.id:
                # ✅ Replay webhook'а → возвращаем существующий
                logger.info(
                    "Idempotent replay: external_id=%s order=%s payment=%s",
                    external_id, order.public_id, existing.public_id,
                )
                return existing
            raise ConflictError("external_id already used by another order", code="external_id_taken", extra={"external_id": external_id})

    # ============================================================
    #  3-4. Проверки статуса заказа
    # ============================================================
    if order.status == OrderStatus.CANCELED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "order_canceled",
                "message": "Cannot pay for a canceled order",
            },
        )

    if order.status != OrderStatus.PENDING:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "order_not_payable",
                "status": order.status.value,
                "message": f"Order in status '{order.status.value}' cannot be paid",
            },
        )

    # ============================================================
    #  5. Создание Payment
    # ============================================================
    # Mock: сразу completed. Реальная интеграция:
    # status=PENDING → шлюз шлёт webhook → handle_webhook переводит в COMPLETED.
    now = datetime.now(timezone.utc)
    payment = Payment(
        order_id=order.id,
        amount=order.total,
        currency="RUB",
        payment_method=method,
        status=PaymentStatus.COMPLETED,
        external_id=external_id,
        paid_at=now,
    )
    db.add(payment)

    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_external_id_conflict(exc):
            if external_id is not None:
                existing = (await db.execute(
                    select(Payment).where(Payment.external_id == external_id)
                )).scalar_one_or_none()
                if existing is not None and existing.order_id == order.id:
                    return existing
            raise ConflictError(
                "external_id already used",
                code="external_id_taken") from exc
        logger.exception("Unexpected IntegrityError on process_payment")
        raise

    # ============================================================
    #  6. Обновляем статус заказа
    # ============================================================
    order.status = OrderStatus.PAID
    await db.flush()

    logger.info(
        "Payment processed: order=%s payment=%s external_id=%s",
        order.public_id, payment.public_id, external_id,
    )

    return payment


def serialize_payment(payment: Payment) -> PaymentResponse:
    """Единая сериализация PaymentResponse — используется в orders и payments."""
    return PaymentResponse(
        public_id=payment.public_id,
        status=payment.status,
        amount=f"{payment.amount:.2f}",
        currency=payment.currency,
        method=payment.payment_method,
        external_id=payment.external_id,
        paid_at=payment.paid_at,
        created_at=payment.created_at,
    )


# ============================================================
#  Внутренние утилиты
# ============================================================

def _is_external_id_conflict(exc: IntegrityError) -> bool:
    """
    Проверяет, что IntegrityError — конфликт partial unique index
    на external_id платежа.

    Аналог `_is_active_name_conflict` и `_is_default_conflict`.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False

    message = str(orig)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) if diag else None

    return (
        constraint_name == _PAYMENT_EXTERNAL_ID_CONSTRAINT
        or _PAYMENT_EXTERNAL_ID_CONSTRAINT in message
    )