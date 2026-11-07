// frontend/src/api/cart.ts
/**
 * Cart API.
 *
 * Все мутации возвращают полное CartResponse — отдельный GET не нужен.
 * Гость/пользователь различаются на бэкенде по cookie/Bearer.
 */
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type {
  CartItemCreate,
  CartItemUpdate,
  CartResponse,
} from "../types/cart";
import type {
  PromoCodePreviewRequest,
  PromoCodePreviewResponse,
} from "../types/promo";

export function fetchCart(): Promise<CartResponse> {
  return apiGet<CartResponse>("/api/v1/cart");
}

export function addCartItem(data: CartItemCreate): Promise<CartResponse> {
  return apiPost<CartResponse>("/api/v1/cart/items", data);
}

export function updateCartItem(
  productId: number,
  data: CartItemUpdate
): Promise<CartResponse> {
  return apiPatch<CartResponse>(`/api/v1/cart/items/${productId}`, data);
}

export function removeCartItem(productId: number): Promise<CartResponse> {
  return apiDelete<CartResponse>(`/api/v1/cart/items/${productId}`);
}

export function clearCart(): Promise<void> {
  return apiDelete<void>("/api/v1/cart");
}

export function applyPromo(
  data: PromoCodePreviewRequest
): Promise<PromoCodePreviewResponse> {
  return apiPost<PromoCodePreviewResponse>("/api/v1/cart/apply-promo", data);
}
