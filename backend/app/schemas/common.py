# app/schemas/common.py
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field

# ✅ Money: >= 0, максимум 10 знаков, 2 после запятой.
# Decimal вместо float — деньги не теряют точность
# (0.1 + 0.2 != 0.3 во float).
Money = Annotated[
    Decimal,
    Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        examples=["1999.99"],
    ),
]


T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    """
    Универсальная обёртка для пагинированных ответов.

    Пример: Paginated[ProductListItem](items=[...], total=100, page=1, page_size=20)
    """
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)