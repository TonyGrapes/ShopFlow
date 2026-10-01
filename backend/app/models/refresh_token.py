# app/models/refresh_token.py
"""
Refresh-токен: хранится хеш, а не raw.

Семья (family_id) — цепочка ротаций одного логина.
Reuse-detection: повторное использование revoked-токена → отзыв всей семьи.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base, TimeStampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ✅ SHA-256 хеш raw-токена. Уникален: один raw → одна строка.
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # ✅ Семья: одна цепочка ротаций от одного логина.
    # Хранится как UUID — генерится при первом логине.
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
    )

    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_family_id", "family_id"),
        
    )