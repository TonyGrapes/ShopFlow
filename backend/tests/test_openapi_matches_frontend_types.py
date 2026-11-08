# tests/test_openapi_matches_frontend_types.py
from functools import lru_cache

import pytest

from app.main import app  # ← импорт вместо фикстуры


@lru_cache
def _openapi_schema():
    return app.openapi()

def test_product_list_item_fields_match_openapi():
    """ProductListItem: поля в OpenAPI совпадают."""
    schema = _openapi_schema()
    product_list_item = schema["components"]["schemas"]["ProductListItem"]

    openapi_fields = set(product_list_item["properties"].keys())
    expected = {"id", "name", "cost", "status", "cover_url", "category"}

    assert openapi_fields == expected


def test_product_price_range_fields_match_openapi():
    """ProductPriceRange: поля в OpenAPI совпадают."""
    schema = _openapi_schema()
    price_range = schema["components"]["schemas"]["ProductPriceRange"]

    assert set(price_range["properties"].keys()) == {"min_cost", "max_cost"}


def test_product_response_fields_match_openapi():
    """ProductResponse: поля совпадают."""
    schema = _openapi_schema()
    product_response = schema["components"]["schemas"]["ProductResponse"]

    openapi_fields = set(product_response["properties"].keys())
    expected = {
        "id", "name", "description", "cost", "category_id",
        "status", "category", "images", "created_at", "updated_at",
    }
    assert openapi_fields == expected


def test_product_status_enum_matches():
    """ProductStatus значения совпадают."""
    schema = _openapi_schema()
    product_status = schema["components"]["schemas"].get("ProductStatus", {})
    if "enum" in product_status:
        values = set(product_status["enum"])
        expected = {"available", "out_of_stock", "discontinued"}
        assert values == expected


# ============================================================
#  Contract: auth / cart / order / address / favorite / payment
# ============================================================

SCHEMA_FIELDS = {
    "RegisterRequest": {
        "email", "password", "first_name", "last_name", "phone_number",
    },
    "LoginRequest": {"email", "password"},
    "TokenResponse": {"access_token", "token_type", "expires_in"},
    "UserResponse": {
        "public_id", "email", "first_name", "last_name", "phone_number",
        "role", "status", "is_email_verified", "created_at",
    },
    "CartItemCreate": {"product_id", "quantity"},
    "CartItemUpdate": {"quantity"},
    "CartItemResponse": {
        "product_id", "name", "cover_url", "quantity", "snapshot_cost",
        "current_cost", "status", "is_available",
    },
    "CartResponse": {
        "items", "total_items", "total_cost", "hidden_items_count",
    },
    "PromoCodePreviewRequest": {"code"},
    "PromoCodePreviewResponse": {
        "code", "discount_type", "discount_value", "subtotal",
        "discount_amount", "final_total",
    },
    "OrderCreate": {"address_id", "promo_code"},
    "OrderItemProductBrief": {"id", "name", "cover_url", "status"},
    "OrderItemResponse": {
        "public_id", "product", "product_cost", "product_count", "created_at",
    },
    "OrderResponse": {
        "public_id", "status", "subtotal", "discount_amount", "total",
        "promo_code", "shipping_address", "items", "payments",
        "created_at", "updated_at",
    },
    "OrderListItem": {
        "public_id", "status", "discount_amount", "total", "items_count",
        "created_at",
    },
    "AddressCreate": {
        "address_line1", "address_line2", "city", "postal_code",
        "country", "is_default",
    },
    "AddressResponse": {
        "id", "address_line1", "address_line2", "city", "postal_code",
        "country", "is_default", "created_at", "updated_at",
    },
    "AddressBrief": {
        "id", "city", "address_line1", "postal_code", "country",
    },
    "FavoriteCreate": {"product_id"},
    "FavoriteResponse": {
        "id", "product_id", "product_name", "cover_url", "cost",
        "status", "created_at",
    },
    "PaymentRequest": {"external_id", "method"},
    "PaymentResponse": {
        "public_id", "status", "amount", "currency", "method",
        "external_id", "paid_at", "created_at",
    },
}


@pytest.mark.parametrize(
    ("schema_name", "expected_fields"),
    sorted(SCHEMA_FIELDS.items()),
)
def test_schema_fields_match_openapi(schema_name, expected_fields):
    """Поля новых фронтенд-типов совпадают с OpenAPI-схемами."""
    schema = _openapi_schema()
    model = schema["components"]["schemas"][schema_name]

    assert set(model["properties"].keys()) == expected_fields


ENUM_VALUES = {
    "UserRole": {"customer", "admin", "moderator", "seller"},
    "UserStatus": {"active", "banned", "pending"},
    "OrderStatus": {"pending", "paid", "shipped", "delivered", "canceled"},
    "PaymentMethod": {"card", "bank_transfer", "crypto", "cash"},
    "PaymentStatus": {"pending", "completed", "failed", "refunded"},
    "DiscountType": {"percentage", "fixed", "free_shipping"},
}


@pytest.mark.parametrize(
    ("enum_name", "expected_values"),
    sorted(ENUM_VALUES.items()),
)
def test_enum_values_match_openapi(enum_name, expected_values):
    """Enum-значения фронтенд-типов совпадают с OpenAPI."""
    schema = _openapi_schema()
    model = schema["components"]["schemas"][enum_name]

    assert set(model["enum"]) == expected_values