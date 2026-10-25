# app/models/order.py
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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
from app.db.enum import OrderStatus

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.order_item import OrderItem
    from app.models.payment import Payment
    from app.models.user import User


class Order(Base, TimeStampMixin):
    __tablename__ = "orders"

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

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )

    # ✅ Финальная сумма после скидки. Не subtotal.
    total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        server_default="0",
        nullable=False
    )

    # ✅ Snapshot промокода: код, а не FK.
    #    Аудит + защита от удаления промокода.
    promo_code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ✅ Скидка. NULL = «скидки не было», не 0.00.
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(
            OrderStatus,
            name="order_status",
            values_callable=lambda x: [e.value for e in x],
            create_type=False
        ),
        server_default=OrderStatus.PENDING.value,
        nullable=False
    )

    shipping_address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id", ondelete="RESTRICT"),
        nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="orders")
    shipping_address: Mapped["Address"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")

    idempotency_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    idempotency_body_hash: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("total >= 0", name="chk_orders_total_non_negative"),
        Index("ix_orders_public_id", "public_id", unique=True),
        Index(
            "uq_orders_user_idempotency_key",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("idx_orders_user_id", "user_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_shipping_address", "shipping_address_id"),
    )