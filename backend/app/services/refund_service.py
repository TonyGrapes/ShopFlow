"""
Сервис возвратов.

Контракт:
- Возврат инициирует только ADMIN/MODERATOR (роутер).
- amount <= payment.amount - sum(existing completed refunds).
- Идемпотентность по external_id: replay → 200 с существующим Refund.
- При полном возврате (sum == payment.amount) payment.status → refunded.
- Order.status НЕ меняем (решение 5-A).

State machine:
- pending → completed
- pending → failed
- completed/failed — терминальные.

Reason валидация: customer_request | defective | wrong_item | other.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.db.enum import PaymentStatus, RefundStatus
from app.models.payment import Payment
from app.models.refund import Refund
from app.schemas.refund import RefundCreate

logger = logging.getLogger(__name__)

_REFUND_EXTERNAL_ID_CONSTRAINT = "idx_refunds_external_id"

_ALLOWED_REASONS = frozenset({
    "customer_request", "defective", "wrong_item", "other",
})


# ============================================================
#  State machine
# ============================================================

_ALLOWED_REFUND_TRANSITIONS: dict[RefundStatus, set[RefundStatus]] = {
    RefundStatus.PENDING:   {RefundStatus.COMPLETED, RefundStatus.FAILED},
    RefundStatus.COMPLETED: set(),   # терминальное
    RefundStatus.FAILED:    set(),   # терминальное
}


def validate_refund_transition(
    current: RefundStatus, new: RefundStatus
) -> None:
    """Проверяет допустимость перехода."""
    if new not in _ALLOWED_REFUND_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_refund_transition",
                "from": current.value,
                "to": new.value,
                "allowed": sorted(
                    s.value for s in _ALLOWED_REFUND_TRANSITIONS[current]
                ),
            },
        )


# ============================================================
#  Создание возврата
# ============================================================

async def _get_refunded_sum(
    db: AsyncSession, payment_id: int
) -> Decimal:
    """
    Сумма уже возвращённых (completed) возвратов по платежу.

    pending/failed НЕ учитываем — они не вернули деньги.
    """
    result = await db.execute(
        select(func.coalesce(func.sum(Refund.amount), Decimal("0.00")))
        .where(
            Refund.payment_id == payment_id,
            Refund.status == RefundStatus.COMPLETED,
        )
    )
    return result.scalar_one()


async def create_refund(
    db: AsyncSession,
    payment: Payment,
    data: RefundCreate,
) -> Refund:
    """
    Создаёт Refund и (mock) сразу переводит в completed.

    Порядок проверок:
    1. external_id replay → возвращаем существующий (200).
    2. payment.status != completed → 422.
    3. reason невалиден → 422.
    4. amount > остатка → 422.
    5. Создание Refund (status=completed, refunded_at=now).
    6. Если sum(refunds) == payment.amount → payment.status = refunded.
    """
    # 1. Идемпотентность
    if data.external_id is not None:
        existing = (await db.execute(
            select(Refund).where(Refund.external_id == data.external_id)
        )).scalar_one_or_none()

        if existing is not None:
            if existing.payment_id == payment.id:
                logger.info(
                    "Idempotent replay: external_id=%s payment=%s refund=%s",
                    data.external_id, payment.public_id, existing.public_id,
                )
                return existing
            raise ConflictError("external_id already used by another refund", code="external_id_taken", extra={"external_id": data.external_id})

    # 2. Платёж должен быть completed
    if payment.status != PaymentStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "payment_not_refundable",
                "status": payment.status.value,
                "message": f"Payment in status '{payment.status.value}' cannot be refunded",
            },
        )

    # 3. Reason
    if data.reason is not None and data.reason not in _ALLOWED_REASONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_refund_reason",
                "reason": data.reason,
                "allowed": sorted(_ALLOWED_REASONS),
            },
        )

    # 4. Amount <= остаток
    already_refunded = await _get_refunded_sum(db, payment.id)
    max_refundable = payment.amount - already_refunded

    if data.amount > max_refundable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "amount_exceeds_remaining",
                "amount": str(data.amount),
                "max_refundable": str(max_refundable),
                "already_refunded": str(already_refunded),
                "payment_amount": str(payment.amount),
            },
        )

    # 5. Создание Refund (mock: сразу completed)
    now = datetime.now(timezone.utc)
    refund = Refund(
        payment_id=payment.id,
        amount=data.amount,
        reason=data.reason,
        status=RefundStatus.COMPLETED,
        external_id=data.external_id,
        refunded_at=now,
    )
    db.add(refund)

    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_external_id_conflict(exc):
            if data.external_id is not None:
                existing = (await db.execute(
                    select(Refund).where(Refund.external_id == data.external_id)
                )).scalar_one_or_none()
                if existing is not None and existing.payment_id == payment.id:
                    return existing
            raise ConflictError("external_id already used", code="external_id_taken") from exc
        logger.exception("Unexpected IntegrityError on create_refund")
        raise

    # 6. Полный возврат → payment.status = refunded
    new_total = already_refunded + data.amount
    if new_total == payment.amount:
        payment.status = PaymentStatus.REFUNDED
        await db.flush()
        logger.info(
            "Payment fully refunded: payment=%s total=%s",
            payment.public_id, new_total,
        )

    return refund


# ============================================================
#  Чтение
# ============================================================

async def get_refund_by_public_id(
    db: AsyncSession, public_id
) -> Refund | None:
    result = await db.execute(
        select(Refund).where(Refund.public_id == public_id)
    )
    return result.scalar_one_or_none()


async def list_refunds_for_payment(
    db: AsyncSession, payment_id: int
) -> list[Refund]:
    """Все возвраты по платежу, свежие первыми."""
    result = await db.execute(
        select(Refund)
        .where(Refund.payment_id == payment_id)
        .order_by(Refund.created_at.desc(), Refund.id.desc())
    )
    return list(result.scalars().all())


# ============================================================
#  Сериализация
# ============================================================

def serialize_refund(refund: Refund):
    """Вернёт RefundResponse. Объявлен в schemas — импорт ленивый."""
    from app.schemas.refund import RefundResponse
    return RefundResponse(
        public_id=refund.public_id,
        payment_id=refund.payment_id,
        amount=refund.amount,
        reason=refund.reason,
        status=refund.status,
        external_id=refund.external_id,
        refunded_at=refund.refunded_at,
        created_at=refund.created_at,
    )


# ============================================================
#  Утилиты
# ============================================================

def _is_external_id_conflict(exc: IntegrityError) -> bool:
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
        constraint_name == _REFUND_EXTERNAL_ID_CONSTRAINT
        or _REFUND_EXTERNAL_ID_CONSTRAINT in message
    )