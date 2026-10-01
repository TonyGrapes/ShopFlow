from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from typing import TYPE_CHECKING, Optional
from datetime import datetime
import uuid

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.user import User


class EmailVerification(Base, TimeStampMixin):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), server_default=text("gen_random_uuid()"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="email_verifications")

    __table_args__ = (
        Index("idx_email_verifications_user_id", "user_id"),
        Index("idx_email_verifications_token", "token", unique=True, postgresql_where=(verified_at.is_(None))),
    )