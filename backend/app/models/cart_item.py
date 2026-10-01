from sqlalchemy import BigInteger,Integer, Index, Text, Numeric, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from decimal import Decimal

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.product import Product


class CartItem(TimeStampMixin, Base):
    __tablename__='cart_items'

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    product_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="cart_items")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_quantity_positive"),
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        Index("idx_cart_items_user_id", "user_id"),
        Index("idx_cart_items_product_id", "product_id"),
    )