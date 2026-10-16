# app/schemas/product.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.db.enum import ProductStatus
from app.schemas.common import Money


class CategoryBrief(BaseModel):
    id: int
    category_name: str
    model_config = ConfigDict(from_attributes=True)


class ProductImageBrief(BaseModel):
    """URL склеивается сервисом из key — не хранится в БД."""
    id: int
    url: str

    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=255,
        description="Название товара",
        examples=["MSI Titan GT77"],
    )
    description: str = Field(min_length=1, max_length=5000)
    cost: Money
    category_id: int = Field(gt=0, description="ID категории")


class ProductCreate(ProductBase):
    status: ProductStatus = ProductStatus.AVAILABLE
    model_config = ConfigDict(extra="forbid")


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    cost: Money | None = None
    status: ProductStatus | None = None
    category_id: int | None = Field(default=None, gt=0)


class ProductResponse(ProductBase):
    id: int
    status: ProductStatus
    category: CategoryBrief | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    images: list[ProductImageBrief] = []

    model_config = ConfigDict(from_attributes=True)


class ProductListItem(BaseModel):
    id: int
    name: str
    cost: Money
    status: ProductStatus
    cover_url: str | None = None          # заполняется сервисом
    model_config = ConfigDict(from_attributes=True)


class ProductBulkStatusUpdate(BaseModel):
    """Bulk update статуса нескольких товаров."""
    product_ids: list[int] = Field(..., min_length=1, max_length=100)
    status: ProductStatus

    model_config = ConfigDict(extra="forbid")


class ProductBulkStatusResponse(BaseModel):
    """Результат bulk update."""
    updated: int           # сколько реально обновлено
    product_ids: list[int] # какие обновились (для отладки)