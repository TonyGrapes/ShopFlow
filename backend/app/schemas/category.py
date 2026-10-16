# app/schemas/category.py
"""
Схемы категорий.

- CategoryCreate: {category_name, parent_id?}
- CategoryUpdate: {category_name?, parent_id?}
- CategoryResponse: плоский
- CategoryTreeResponse: рекурсивный
"""
from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=255)
    parent_id: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(extra="forbid")


class CategoryUpdate(BaseModel):
    category_name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(extra="forbid")


class CategoryResponse(BaseModel):
    id: int
    category_name: str
    path: str
    parent_id: int | None

    model_config = ConfigDict(from_attributes=True)


class CategoryTreeResponse(BaseModel):
    id: int
    category_name: str
    path: str
    children: list["CategoryTreeResponse"] = []


CategoryTreeResponse.model_rebuild()