from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType
from sqlalchemy_utils import Ltree

from app.db.base import Base, TimeStampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class LtreeType(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return 'ltree'

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return str(value)
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return Ltree(value)
        return process


class Category(TimeStampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    path: Mapped[Ltree] = mapped_column(LtreeType, nullable=False)

    category_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Связи
    parent: Mapped[Optional["Category"]] = relationship(
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent",
        cascade="save-update, merge",
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="category",
        cascade="save-update, merge",
    )

    __table_args__ = (
        UniqueConstraint("path", name="uq_categories_path"),
        Index("path_gist_idx", "path", postgresql_using="gist"),
        Index("path_idx", "path", postgresql_using="btree"),
        Index("idx_categories_parent_id", "parent_id"),
    )