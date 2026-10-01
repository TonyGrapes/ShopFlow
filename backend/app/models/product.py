# app/models/product.py
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin
from app.db.enum import ProductStatus

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.review import Review


class Product(TimeStampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(
            ProductStatus,
            name="product_status",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        server_default=ProductStatus.OUTOFSTOCK.value,
        nullable=False,
    )

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    category: Mapped["Category"] = relationship(back_populates="products")
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_product_category_id", "category_id"),
        Index("idx_product_status", "status"),
        Index(
            "idx_product_active_name",
            "name",
            unique=True,
            postgresql_where=(deleted_at.is_(None)),
        ),
    )

    @property
    def cover_key(self) -> str | None:
        """✅ Возвращает KEY первой картинки — URL склеивается в сервисе."""
        if self.images:
            return self.images[0].key
        return None


class ProductImage(TimeStampMixin, Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(
        "image_id", BigInteger, primary_key=True, autoincrement=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    # ✅ image_url УБРАН — URL производная, не хранится
    # ✅ reviews УБРАН — отзывы принадлежат Product, не ProductImage

    product: Mapped["Product"] = relationship(back_populates="images")

    __table_args__ = (Index("idx_product_image_product_id", "product_id"),)