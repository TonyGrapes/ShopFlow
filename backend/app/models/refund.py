import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin
from app.db.enum import RefundStatus

if TYPE_CHECKING:
    from app.models.payment import Payment


class Refund(TimeStampMixin, Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )

    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        CheckConstraint(
            "reason IN ('customer_request', 'defective', 'wrong_item', 'other')",
            name="chk_refund_reason"
        ),
        nullable=True
    )

    status: Mapped[RefundStatus] = mapped_column(
        SAEnum(
            RefundStatus,
            name="refund_status",
            values_callable=lambda x: [e.value for e in x],
            create_type=False
        ),
        server_default=RefundStatus.PENDING.value,
        nullable=False    
    )

    external_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    payment: Mapped["Payment"] = relationship(back_populates="refunds")


    __table_args__ = (
        Index("ix_refunds_public_id", "public_id", unique=True),
        Index("idx_refunds_payment_id", "payment_id"),
        Index("idx_refunds_status", "status"),
        Index(
            "idx_refunds_external_id",
            "external_id",
            unique=True,
            postgresql_where=(external_id.isnot(None)),
        ),
    )