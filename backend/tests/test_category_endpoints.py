# tests/test_category_endpoints.py
"""
HTTP-тесты /api/v1/categories и /api/v1/admin/categories.

Публичные:
- GET /categories          — плоский список
- GET /categories/tree     — дерево

Админские (require_roles ADMIN, MODERATOR):
- POST   /admin/categories
- PATCH  /admin/categories/{id}
- DELETE /admin/categories/{id}
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.category import Category
from app.models.product import Product


# ============================================================
#  GET /categories — публичный
# ============================================================

class TestListCategoriesEndpoint:
    """GET /api/v1/categories."""

    @pytest.mark.asyncio
    async def test_empty(self, client):
        response = await client.get("/api/v1/categories")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_public_no_auth(self, client, category_root):
        """Публичный — без токена."""
        response = await client.get("/api/v1/categories")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["category_name"] == "Electronics"
        assert body[0]["path"] == "electronics"
        assert body[0]["parent_id"] is None

    @pytest.mark.asyncio
    async def test_hierarchical_order(
        self, client, category_root, category_child, category_grandchild,
        category_for_admin
    ):
        response = await client.get("/api/v1/categories")
        paths = [c["path"] for c in response.json()]
        assert paths == [
            "electronics",
            "electronics.laptops",
            "electronics.laptops.gaming",
            "furniture",
        ]


# ============================================================
#  GET /categories/tree
# ============================================================

class TestGetCategoryTreeEndpoint:
    """GET /api/v1/categories/tree."""

    @pytest.mark.asyncio
    async def test_empty(self, client):
        response = await client.get("/api/v1/categories/tree")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_nested_tree(
        self, client, category_root, category_child, category_grandchild
    ):
        response = await client.get("/api/v1/categories/tree")
        assert response.status_code == 200
        tree = response.json()
        assert len(tree) == 1
        root = tree[0]
        assert root["category_name"] == "Electronics"
        assert len(root["children"]) == 1

        child = root["children"][0]
        assert child["category_name"] == "Laptops"
        assert len(child["children"]) == 1

        grand = child["children"][0]
        assert grand["category_name"] == "Gaming Laptops"


# ============================================================
#  POST /admin/categories
# ============================================================

class TestCreateCategoryEndpoint:
    """POST /api/v1/admin/categories."""

    @pytest.mark.asyncio
    async def test_create_root(self, client, admin_headers):
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Electronics"},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["category_name"] == "Electronics"
        assert body["path"] == "electronics"
        assert body["parent_id"] is None

    @pytest.mark.asyncio
    async def test_create_child(self, client, admin_headers, category_root):
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Laptops", "parent_id": category_root.id},
            headers=admin_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["path"] == "electronics.laptops"
        assert body["parent_id"] == category_root.id

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client):
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Hack"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_requires_admin_role(
        self, client, auth_headers
    ):
        """CUSTOMER → 403."""
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Hack"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_invalid_parent_422(
        self, client, admin_headers
    ):
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Orphan", "parent_id": 999999},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_parent"

    @pytest.mark.asyncio
    async def test_create_duplicate_409(
        self, client, admin_headers, category_root
    ):
        await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Laptops", "parent_id": category_root.id},
            headers=admin_headers,
        )
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "Laptops", "parent_id": category_root.id},
            headers=admin_headers,
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_rejects_extra_fields(
        self, client, admin_headers
    ):
        response = await client.post(
            "/api/v1/admin/categories",
            json={"category_name": "X", "hacker": "field"},
            headers=admin_headers,
        )
        assert response.status_code == 422


# ============================================================
#  PATCH /admin/categories/{id}
# ============================================================

class TestUpdateCategoryEndpoint:
    """PATCH /api/v1/admin/categories/{id}."""

    @pytest.mark.asyncio
    async def test_rename(
        self, client, admin_headers, category_root: Category
    ):
        response = await client.patch(
            f"/api/v1/admin/categories/{category_root.id}",
            json={"category_name": "Электроника"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["category_name"] == "Электроника"
        assert body["path"] == "electronics"   # path не меняется

    @pytest.mark.asyncio
    async def test_move(
        self, client, admin_headers, category_child, category_for_admin
    ):
        response = await client.patch(
            f"/api/v1/admin/categories/{category_child.id}",
            json={"parent_id": category_for_admin.id},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["path"] == "furniture.laptops"
        assert body["parent_id"] == category_for_admin.id

    @pytest.mark.asyncio
    async def test_move_missing_404(self, client, admin_headers):
        response = await client.patch(
            "/api/v1/admin/categories/999999",
            json={"category_name": "X"},
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_self_parent_422(
        self, client, admin_headers, category_root
    ):
        response = await client.patch(
            f"/api/v1/admin/categories/{category_root.id}",
            json={"parent_id": category_root.id},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "self_parent"

    @pytest.mark.asyncio
    async def test_cycle_422(
        self, client, admin_headers, category_root, category_grandchild
    ):
        response = await client.patch(
            f"/api/v1/admin/categories/{category_root.id}",
            json={"parent_id": category_grandchild.id},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "cycle_detected"

    @pytest.mark.asyncio
    async def test_requires_admin(
        self, client, auth_headers, category_root
    ):
        response = await client.patch(
            f"/api/v1/admin/categories/{category_root.id}",
            json={"category_name": "Hacked"},
            headers=auth_headers,
        )
        assert response.status_code == 403


# ============================================================
#  DELETE /admin/categories/{id}
# ============================================================

class TestDeleteCategoryEndpoint:
    """DELETE /api/v1/admin/categories/{id}."""

    @pytest.mark.asyncio
    async def test_delete_leaf(
        self, client, admin_headers, category_grandchild: Category
    ):
        response = await client.delete(
            f"/api/v1/admin/categories/{category_grandchild.id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_missing_404(self, client, admin_headers):
        response = await client.delete(
            "/api/v1/admin/categories/999999",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_with_products_409(
        self, client, db_session, admin_headers, category_grandchild
    ):
        """У категории есть товар → 409."""
        from decimal import Decimal

        from app.models.product import Product

        db_session.add(Product(
            name="Test Product",
            description="Test",
            cost=Decimal("100.00"),
            category_id=category_grandchild.id,
        ))
        await db_session.flush()

        response = await client.delete(
            f"/api/v1/admin/categories/{category_grandchild.id}",
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "category_has_products"  # или has_products

    @pytest.mark.asyncio
    async def test_delete_with_children_409(
        self, client, admin_headers, category_root, category_child
    ):
        response = await client.delete(
            f"/api/v1/admin/categories/{category_root.id}",
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "category_has_children"
    

    @pytest.mark.asyncio
    async def test_requires_admin(
        self, client, auth_headers, category_grandchild
    ):
        response = await client.delete(
            f"/api/v1/admin/categories/{category_grandchild.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403