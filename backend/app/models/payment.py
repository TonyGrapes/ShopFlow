from sqlalchemy import BigInteger, Numeric, Text, DateTime, ForeignKey, Index, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, Optional
from datetime import datetime
from decimal import Decimal

from app.db.base import Base, TimeStampMixin
from app.db.enum import PaymentMethod, PaymentStatus

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.refund import Refund


class Payment(TimeStampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        Text,
        server_default="RUB",
        nullable=False
    )

    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(
            PaymentMethod,
            name="payment_method",
            values_callable=lambda x: [e.value for e in x],
            create_type=False
        ),
        nullable=False
    )

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(
            PaymentStatus,
            name="payment_status",
            values_callable=lambda x: [e.value for e in x],
            create_type=False
        ),
        server_default=PaymentStatus.PENDING.value,
        nullable=False
    )

    external_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="payments")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_payments_order_id", "order_id"),
        Index("idx_payments_status", "status"),
        # Уникальный external_id только для не-null значений
        Index("idx_payments_external_id", "external_id", unique=True, postgresql_where=(external_id.isnot(None))),
    )

