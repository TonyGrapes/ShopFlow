from sqlalchemy import BigInteger, Integer, Text, Boolean, DateTime, ForeignKey, Index, CheckConstraint, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, Optional
from datetime import datetime

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.product import Product
    from app.models.order import Order


class Review(TimeStampMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # CHECK в __table_args__
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="reviews")
    product: Mapped["Product"] = relationship(back_populates="reviews")
    order: Mapped[Optional["Order"]] = relationship()

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="chk_review_rating_range"),
        Index(
            "uq_review_user_product",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=(deleted_at.is_(None))
        ),
        Index("idx_reviews_product_id", "product_id"),
        Index("idx_reviews_user_id", "user_id"),
        Index("idx_reviews_rating", "rating"),
    )