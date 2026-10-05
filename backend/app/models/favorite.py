# app/models/favorite.py
"""
Избранное. Только для залогиненных пользователей.

Hard delete через UNIQUE (user_id, product_id): пользователь либо
имеет товар в избранном, либо нет. Soft delete здесь создал бы
проблему "нельзя снова добавить удалённый favorite" без partial index.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ✅ updated_at не нужен: запись либо есть, либо нет.
    #    created_at — единственная полезная метка.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ✅ Relationship для JOIN при чтении списка (с фильтром soft-deleted)
    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship(back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),
        Index("idx_favorites_user_id", "user_id"),
        Index("idx_favorites_product_id", "product_id"),
    )