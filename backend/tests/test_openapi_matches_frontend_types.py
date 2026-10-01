# tests/test_openapi_matches_frontend_types.py
import json
from pathlib import Path

import pytest

from app.main import app   # ← импорт вместо фикстуры


def test_product_list_item_fields_match_openapi():
    """ProductListItem: поля в OpenAPI совпадают."""
    schema = app.openapi()   # ← используем импортированный app
    product_list_item = schema["components"]["schemas"]["ProductListItem"]

    openapi_fields = set(product_list_item["properties"].keys())
    expected = {"id", "name", "cost", "status", "cover_url"}

    assert openapi_fields == expected


def test_product_response_fields_match_openapi():
    """ProductResponse: поля совпадают."""
    schema = app.openapi()
    product_response = schema["components"]["schemas"]["ProductResponse"]

    openapi_fields = set(product_response["properties"].keys())
    expected = {
        "id", "name", "description", "cost", "category_id",
        "status", "category", "images", "created_at", "updated_at",
    }
    assert openapi_fields == expected


def test_product_status_enum_matches():
    """ProductStatus значения совпадают."""
    schema = app.openapi()
    product_status = schema["components"]["schemas"].get("ProductStatus", {})
    if "enum" in product_status:
        values = set(product_status["enum"])
        expected = {"available", "out_of_stock", "discontinued"}
        assert values == expected