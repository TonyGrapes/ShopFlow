# app/schemas/address.py
"""
Схемы адресов доставки.

Address используется как самостоятельная сущность (CRUD /addresses)
и как вложенный объект в OrderResponse.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AddressCreate(BaseModel):
    address_line1: str = Field(..., min_length=1, max_length=500)
    address_line2: str | None = Field(default=None, max_length=500)
    city: str = Field(..., min_length=1, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=1, max_length=100)
    is_default: bool = False

    model_config = ConfigDict(extra="forbid")


class AddressUpdate(BaseModel):
    address_line1: str | None = Field(default=None, min_length=1, max_length=500)
    address_line2: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    is_default: bool | None = None

    model_config = ConfigDict(extra="forbid")


class AddressResponse(BaseModel):
    id: int
    address_line1: str
    address_line2: str | None
    city: str
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddressBrief(BaseModel):
    """Облегчённая версия для вложения в OrderResponse."""
    id: int
    city: str
    address_line1: str
    postal_code: str
    country: str

    model_config = ConfigDict(from_attributes=True)