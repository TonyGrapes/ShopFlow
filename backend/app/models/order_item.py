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
    Integer,
    Numeric,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.product import Product


class OrderItem(TimeStampMixin, Base):
    __tablename__ = "order_items"

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

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )

    product_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    product_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        CheckConstraint("product_cost >= 0", name="chk_order_items_cost_non_negative"),
        CheckConstraint("product_count > 0", name="chk_order_item_count_positive"),
        UniqueConstraint("order_id", "product_id", name="uq_order_item_product"),
        Index("idx_order_items_order_id", "order_id"),
        Index("idx_order_items_product_id", "product_id"),
        Index("ix_order_items_public_id", "public_id", unique=True),
    )