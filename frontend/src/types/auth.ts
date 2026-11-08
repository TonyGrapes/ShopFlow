// frontend/src/types/auth.ts
/**
 * Типы, синхронные с backend app/schemas/auth.py и app/db/enum.py.
 *
 * ВАЖНО: refresh-токен НЕ приходит в JSON — он живёт в httpOnly-cookie.
 * Access-токен хранится только в памяти фронтенда.
 */

// app/db/enum.py — UserRole
export type UserRole = "customer" | "admin" | "moderator" | "seller";

// app/db/enum.py — UserStatus
export type UserStatus = "active" | "banned" | "pending";

// app/schemas/auth.py — RegisterRequest
export interface RegisterRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  phone_number: string;
}

// app/schemas/auth.py — LoginRequest
export interface LoginRequest {
  email: string;
  password: string;
}

// app/schemas/auth.py — TokenResponse
export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// app/schemas/auth.py — UserResponse
export interface UserResponse {
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

// app/schemas/auth.py — MessageResponse
export interface MessageResponse {
  message: string;
}

// app/schemas/auth.py — ResendVerificationRequest
export interface ResendVerificationRequest {
  email: string;
}

// app/schemas/auth.py — ProfileUpdateRequest
export interface ProfileUpdateRequest {
  first_name?: string | null;
  last_name?: string | null;
  phone_number?: string | null;
}

// app/schemas/auth.py — PasswordChangeRequest
export interface PasswordChangeRequest {
  old_password: string;
  new_password: string;
}
