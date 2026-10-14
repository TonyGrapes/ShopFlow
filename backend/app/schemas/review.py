"""
Схемы отзывов.

Review — только для аутентифицированных, только после delivered-заказа.
Редактирование запрещено (нет ReviewUpdate).
Удаление — soft-delete (и юзером, и модератором).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    """
    Вход для POST /reviews.

    product_id, rating обязательны. title/comment опциональны.
    Backend находит последний delivered-заказ с этим товаром и
    ставит is_verified=True.
    """
    product_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=255)
    comment: str | None = Field(default=None, max_length=5000)

    model_config = ConfigDict(extra="forbid")


class ReviewUserBrief(BaseModel):
    """Минимальный публичный профиль автора. Без email/телефона."""
    public_id: UUID
    first_name: str
    last_name: str

    model_config = ConfigDict(from_attributes=True)


class ReviewResponse(BaseModel):
    public_id: UUID
    product_id: int
    user: ReviewUserBrief
    rating: int
    title: str | None
    comment: str | None
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewSummaryResponse(BaseModel):
    """
    Агрегат по отзывам товара.

    avg_rating — средний, округлён до 2 знаков.
    distribution — сколько отзывов с каждой оценкой (1..5).
    Все пять ключей всегда присутствуют, даже если 0.
    """
    avg_rating: float
    total_count: int
    distribution: dict[int, int]