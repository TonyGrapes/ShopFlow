// frontend/src/api/categories.ts
import { apiGet } from "./client";
import type { Category, CategoryTree } from "../types/category";

/** GET /api/v1/categories — плоский список, ORDER BY path. */
export function fetchCategories(): Promise<Category[]> {
  return apiGet<Category[]>("/api/v1/categories");
}

/** GET /api/v1/categories/tree — иерархия категорий. */
export function fetchCategoryTree(): Promise<CategoryTree[]> {
  return apiGet<CategoryTree[]>("/api/v1/categories/tree");
}
