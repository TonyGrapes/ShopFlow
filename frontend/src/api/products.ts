// frontend/src/api/products.ts
import { apiGet } from "./client";
import type {
  Paginated,
  ProductListParams,
  ProductListItem,
  ProductResponse,
} from "../types/product";

/**
 * GET /api/v1/products — список с фильтрами и пагинацией.
 */
export async function fetchProductList(
  params: ProductListParams = {}
): Promise<Paginated<ProductListItem>> {
  return apiGet<Paginated<ProductListItem>>("/api/v1/products", params);
}

/**
 * GET /api/v1/products/{id} — детали товара.
 *
 * @throws ApiError 404 если товар не найден или удалён
 */
export async function fetchProduct(id: number): Promise<ProductResponse> {
  return apiGet<ProductResponse>(`/api/v1/products/${id}`);
}