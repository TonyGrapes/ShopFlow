// frontend/src/api/admin.ts
/**
 * Admin/store-manager endpoints.
 *
 * Access is enforced by the backend (ADMIN / MODERATOR). The frontend guard
 * only hides navigation; it is never the security boundary.
 */
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { Paginated } from "../types/common";
import type { Category } from "../types/category";
import type {
  OrderListItem,
  OrderResponse,
  OrderStatus,
} from "../types/order";

export interface AdminOrderListParams {
  page?: number;
  page_size?: number;
  status?: OrderStatus;
  user_id?: number;
}

export interface CategoryWrite {
  category_name: string;
  parent_id?: number | null;
}

export function listAdminOrders(
  params: AdminOrderListParams = {}
): Promise<Paginated<OrderListItem>> {
  return apiGet<Paginated<OrderListItem>>("/api/v1/admin/orders", params);
}

export function updateAdminOrderStatus(
  publicId: string,
  status: OrderStatus
): Promise<OrderResponse> {
  return apiPatch<OrderResponse>(`/api/v1/admin/orders/${publicId}/status`, {
    status,
  });
}

export function createCategory(data: CategoryWrite): Promise<Category> {
  return apiPost<Category>("/api/v1/admin/categories", data);
}

export function updateCategory(
  categoryId: number,
  data: Partial<CategoryWrite>
): Promise<Category> {
  return apiPatch<Category>(`/api/v1/admin/categories/${categoryId}`, data);
}

export function deleteCategory(categoryId: number): Promise<void> {
  return apiDelete<void>(`/api/v1/admin/categories/${categoryId}`);
}
