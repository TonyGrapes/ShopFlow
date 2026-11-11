/**
 * Админ-типы, синхронные с backend app/schemas/admin.py.
 */
import type { UserRole, UserStatus } from "./auth";

// app/schemas/admin.py — AdminUserListItem
export interface AdminUserListItem {
  public_id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  role: UserRole;
  status: UserStatus;
  is_email_verified: boolean;
  created_at: string;
}

// app/schemas/admin.py — UserRoleUpdateRequest
export interface UserRoleUpdateRequest {
  role: UserRole;
}

// app/schemas/admin.py — UserStatusUpdateRequest
export interface UserStatusUpdateRequest {
  status: UserStatus;
}

// Query-параметры GET /api/v1/admin/users
export interface AdminUserListParams {
  page?: number;
  page_size?: number;
  role?: UserRole;
  status?: UserStatus;
}

// Query-параметры GET /api/v1/admin/products
export interface AdminProductListParams {
  page?: number;
  page_size?: number;
  q?: string;
  category_id?: number;
  status?: string;
}

// ============================================================
//  app/schemas/admin.py — Dashboard (C1)
// ============================================================
import type { Money } from "./common";

export interface TopProductItem {
  product_id: number;
  product_name: string;
  total_quantity: number;
  total_revenue: Money;
}

export interface AdminDashboardResponse {
  period_days: number;
  orders_count: number;
  revenue_gross: Money;
  refunds_total: Money;
  revenue_net: Money;
  new_users_count: number;
  top_products: TopProductItem[];
}