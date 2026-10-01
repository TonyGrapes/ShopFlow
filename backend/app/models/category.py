from sqlalchemy_utils import Ltree
from sqlalchemy import BigInteger,Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType
from app.db.base import Base, TimeStampMixin

from typing import TYPE_CHECKING

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

    path: Mapped[Ltree] = mapped_column(LtreeType, nullable=False)

    category_name: Mapped[str] = mapped_column(Text, nullable=False)

    products: Mapped[list['Product']] = relationship(back_populates='category', cascade="save-update, merge")


    __table_args__ = (
        UniqueConstraint("path", name="uq_categories_path"),
        Index(
            'path_gist_idx',
            'path',
            postgresql_using='gist'
        ),
        Index(
            'path_idx',
            'path',
            postgresql_using='btree'
        ),
    )


