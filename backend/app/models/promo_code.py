from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, Integer, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimeStampMixin
from app.db.enum import DiscountType


class PromoCode(TimeStampMixin, Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False
        )    
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    
    discount_type: Mapped[DiscountType] = mapped_column(
        SAEnum(
            DiscountType, name="discount_type", 
            values_callable=lambda x: [e.value for e in x], create_type=False
            ),
        nullable=False
    )
    
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # 10% или 100₽
    min_order_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

    __table_args__ = (
        CheckConstraint(
        "discount_type != 'percentage' OR (discount_value >= 1 AND discount_value <= 100)",
        name="chk_promo_percentage_range",
        ),
        CheckConstraint("discount_value > 0", name="chk_promo_discount_positive"),
        CheckConstraint("valid_until > valid_from", name="chk_promo_valid_dates"),
        Index("idx_promo_codes_active", "is_active", postgresql_where=(is_active.is_(True))),
    )