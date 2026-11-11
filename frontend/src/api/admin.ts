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
import type { 
  ProductListItem,
  ProductResponse,
  ProductCreate,
  ProductUpdate,
} from "../types/product";
import type {
  AdminUserListItem,
  AdminUserListParams,
  AdminProductListParams,
  UserRoleUpdateRequest,
  UserStatusUpdateRequest,
} from "../types/admin";

import type { AdminDashboardResponse } from "../types/admin";

import type { AdminDashboardSeriesResponse } from "../types/admin";
import { API_BASE_URL } from "./config";

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

// ============================================================
//  Admin products
// ============================================================

export function listAdminProducts(
  params: AdminProductListParams = {}
): Promise<Paginated<ProductListItem>> {
  return apiGet<Paginated<ProductListItem>>("/api/v1/admin/products", params);
}

export function createAdminProduct(
  data: ProductCreate
): Promise<ProductResponse> {
  return apiPost<ProductResponse>("/api/v1/admin/products", data);
}

export function updateAdminProduct(
  productId: number,
  data: ProductUpdate
): Promise<ProductResponse> {
  return apiPatch<ProductResponse>(
    `/api/v1/admin/products/${productId}`,
    data
  );
}

export function deleteAdminProduct(productId: number): Promise<void> {
  return apiDelete<void>(`/api/v1/admin/products/${productId}`);
}

// ============================================================
//  Admin users
// ============================================================

export function listAdminUsers(
  params: AdminUserListParams = {}
): Promise<Paginated<AdminUserListItem>> {
  return apiGet<Paginated<AdminUserListItem>>("/api/v1/admin/users", params);
}

export function updateUserRole(
  publicId: string,
  data: UserRoleUpdateRequest
): Promise<AdminUserListItem> {
  return apiPatch<AdminUserListItem>(
    `/api/v1/admin/users/${publicId}/role`,
    data
  );
}

export function updateUserStatus(
  publicId: string,
  data: UserStatusUpdateRequest
): Promise<AdminUserListItem> {
  return apiPatch<AdminUserListItem>(
    `/api/v1/admin/users/${publicId}/status`,
    data
  );
}

export function fetchAdminDashboard(
  periodDays = 7
): Promise<AdminDashboardResponse> {
  return apiGet<AdminDashboardResponse>("/api/v1/admin/dashboard", {
    period_days: periodDays,
  });
}

export function fetchAdminDashboardSeries(
  periodDays = 7
): Promise<AdminDashboardSeriesResponse> {
  return apiGet<AdminDashboardSeriesResponse>(
    "/api/v1/admin/dashboard/series",
    { period_days: periodDays }
  );
}

export async function downloadDashboardCsv(
  periodDays = 7
): Promise<void> {
  // access-токен в памяти, не в cookies → нельзя window.location.href.
  // Используем fetch + blob + <a download>.
  const { getAccessToken } = await import("./session");
  const token = getAccessToken();
  const url = `${API_BASE_URL}/api/v1/admin/dashboard/export.csv?period_days=${periodDays}`;
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `shopflow-dashboard-${periodDays}d.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}



