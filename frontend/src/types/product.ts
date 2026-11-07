// frontend/src/types/product.ts
/**
 * Типы, синхронные с backend Pydantic-схемами.
 *
 * Источник правды: app/schemas/product.py и app/schemas/common.py
 * При изменении схем — обновлять здесь.
 *
 * Синхронность проверяется тестом
 * tests/test_openapi_matches_frontend_types.py (на backend).
 */
import type { Money } from "./common";

// Money и Paginated вынесены в common.ts, но реэкспортируются
// для обратной совместимости с существующими импортами.
export type { Money, Paginated } from "./common";

// ============================================================
//  app/db/enum.py — ProductStatus
// ============================================================
export type ProductStatus =
  | "out_of_stock"
  | "available"
  | "discontinued";

// ============================================================
//  app/schemas/product.py — CategoryBrief
// ============================================================
export interface CategoryBrief {
  id: number;
  category_name: string;
}

// ============================================================
//  app/schemas/product.py — ProductImageBrief
// ============================================================
export interface ProductImageBrief {
  id: number;
  url: string;
}

// ============================================================
//  app/schemas/product.py — ProductListItem
// ============================================================
export interface ProductListItem {
  id: number;
  name: string;
  cost: Money;
  status: ProductStatus;
  cover_url: string | null;
  category: CategoryBrief | null;
}

// ============================================================
//  app/schemas/product.py — ProductPriceRange
// ============================================================
export interface ProductPriceRange {
  min_cost: Money | null;
  max_cost: Money | null;
}

// ============================================================
//  app/schemas/product.py — ProductResponse
// ============================================================
export interface ProductResponse {
  id: number;
  name: string;
  description: string;
  cost: Money;
  category_id: number;
  status: ProductStatus;
  category: CategoryBrief | null;
  images: ProductImageBrief[];
  created_at: string | null;      // ISO 8601
  updated_at: string | null;
}

// ============================================================
//  Query-параметры для GET /api/v1/products
// ============================================================
export interface ProductListParams {
  page?: number;
  page_size?: number;
  q?: string;
  category_id?: number;
  min_cost?: Money;
  max_cost?: Money;
  status?: ProductStatus;
  sort_by?: "id" | "name" | "cost" | "created_at";
  sort_order?: "asc" | "desc";
}