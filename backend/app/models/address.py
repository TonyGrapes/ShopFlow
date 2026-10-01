from sqlalchemy import BigInteger, Boolean, String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Address(TimeStampMixin, Base):
    __tablename__='addresses'

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    address_line1: Mapped[str] = mapped_column(Text, nullable=False)
    address_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    postal_code: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default='false', nullable=False)
    user: Mapped["User"] = relationship(back_populates="addresses")

    __table_args__  = (
        Index("idx_addresses_user_id", "user_id"),
        Index("idx_one_default_address_per_user", "user_id", unique=True, postgresql_where=(is_default.is_(True))),

    )