import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin
from app.db.enum import UserRole, UserStatus

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.cart_item import CartItem
    from app.models.email_verification import EmailVerification
    from app.models.favorite import Favorite
    from app.models.order import Order
    from app.models.refresh_token import RefreshToken
    from app.models.review import Review



class User(TimeStampMixin, Base):
    __tablename__= "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        unique=True,
        nullable=False
    )

    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)

    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        SAEnum(
            UserStatus,
            name='userstatus',
            values_callable=lambda x: [e.value for e in x],
            create_type=False
            ),
        nullable=False, 
        default=UserStatus.ACTIVE, 
        server_default=UserStatus.ACTIVE.value  # ENUM'ы нужно передавать как строки
    )

    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text('false')
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name='userrole',
            values_callable=lambda x: [e.value for e in x],
            create_type=False
            ),
        nullable=False,
        default=UserRole.CUSTOMER,
        server_default=UserRole.CUSTOMER.value
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
        # ✅ SCHEMA-01: НЕ "all, delete-orphan" — заказы не удаляются
        # с юзером (история покупок). FK orders.user_id ON DELETE RESTRICT
        # в БД дополнительно защищает. Удаление юзера с заказами
        # запрещено на уровне БД, а не ORM.
    orders: Mapped[list["Order"]] = relationship(back_populates="user", cascade="save-update, merge")
    reviews: Mapped[list["Review"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    email_verifications: Mapped[list["EmailVerification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index(
            'idx_users_active_email',
            'email',
            unique=True,
            postgresql_where=(deleted_at.is_(None))
        ),
        Index(
            'idx_users_active_phone',
            'phone_number',
            unique=True,
            postgresql_where=(deleted_at.is_(None))
        ),
    )

    