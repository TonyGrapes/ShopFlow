# app/schemas/favorite.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FavoriteCreate(BaseModel):
    product_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class FavoriteResponse(BaseModel):
    """Позиция избранного. product встроен, чтобы UI не делал N+1."""
    id: int
    product_id: int
    product_name: str
    cover_url: str | None = None
    cost: str
    status: str
    created_at: datetime