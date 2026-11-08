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