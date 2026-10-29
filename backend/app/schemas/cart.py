
from pydantic import BaseModel, ConfigDict, Field

from app.db.enum import ProductStatus
from app.schemas.common import Money


class CartItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)

    model_config = ConfigDict(extra="forbid")


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=0, le=100)   # 0 = удалить позицию

    model_config = ConfigDict(extra="forbid")


class CartItemResponse(BaseModel):
    """
    Позиция корзины.

    snapshot_cost — снимок цены в момент добавления.
    current_cost — текущая цена в каталоге.
    Если они различаются, UI может показать предупреждение.
    """
    product_id: int
    name: str
    cover_url: str | None = None
    quantity: int
    snapshot_cost: Money
    current_cost: Money
    status: ProductStatus
    is_available: bool                 # не удалён и status == available

    model_config = ConfigDict(from_attributes=True)


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total_items: int                   # сумма quantity по видимым позициям
    total_cost: Money                  # сумма snapshot_cost * quantity
    hidden_items_count: int = 0        # сколько soft-deleted отфильтровано