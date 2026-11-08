// frontend/src/api/auth.ts
/**
 * Auth API.
 *
 * login/register/logout помечены auth:false и skipAuthRefresh:true:
 * для них бессмысленно прикладывать access-токен и опасно
 * пытаться обновлять сессию при 401.
 */
import { apiGet, apiPatch, apiPost } from "./client";
import { refreshAccessToken } from "./session";
import type {
  LoginRequest,
  MessageResponse,
  RegisterRequest,
  ResendVerificationRequest,
  TokenResponse,
  UserResponse,
  ProfileUpdateRequest,
  PasswordChangeRequest,
} from "../types/auth";

export function registerUser(data: RegisterRequest): Promise<UserResponse> {
  return apiPost<UserResponse>("/api/v1/auth/register", data, {
    auth: false,
    skipAuthRefresh: true,
  });
}

export function loginUser(data: LoginRequest): Promise<TokenResponse> {
  return apiPost<TokenResponse>("/api/v1/auth/login", data, {
    auth: false,
    skipAuthRefresh: true,
  });
}

export function logoutUser(): Promise<MessageResponse> {
  return apiPost<MessageResponse>("/api/v1/auth/logout", undefined, {
    auth: false,
    skipAuthRefresh: true,
  });
}

export function fetchMe(): Promise<UserResponse> {
  return apiGet<UserResponse>("/api/v1/auth/me");
}

export function refreshSession(): Promise<TokenResponse | null> {
  return refreshAccessToken();
}

export function resendVerification(
  data: ResendVerificationRequest
): Promise<MessageResponse> {
  return apiPost<MessageResponse>("/api/v1/auth/resend-verification", data, {
    auth: false,
    skipAuthRefresh: true,
  });
}

export function verifyEmail(token: string): Promise<MessageResponse> {
  return apiGet<MessageResponse>("/api/v1/auth/verify-email", { token });
}

// Защита от двойного вызова в React StrictMode: токен одноразовый,
// повторный GET вернул бы 400 «Invalid or used token».
const verificationPromises = new Map<string, Promise<MessageResponse>>();

export function verifyEmailOnce(token: string): Promise<MessageResponse> {
  const existing = verificationPromises.get(token);
  if (existing !== undefined) {
    return existing;
  }
  const promise = verifyEmail(token);
  verificationPromises.set(token, promise);
  return promise;
}

export function updateProfile(
  data: ProfileUpdateRequest
): Promise<UserResponse> {
  return apiPatch<UserResponse>("/api/v1/auth/me", data);
}

export function changePassword(
  data: PasswordChangeRequest
): Promise<MessageResponse> {
  return apiPost<MessageResponse>("/api/v1/auth/change-password", data);
}