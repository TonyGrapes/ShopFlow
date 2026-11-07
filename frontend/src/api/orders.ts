// frontend/src/api/orders.ts
/**
 * Orders + payments API.
 *
 * Создание заказа поддерживает Idempotency-Key (опциональный header).
 * Оплата — POST /orders/{public_id}/pay (mock, сразу completed).
 */
import { apiGet, apiPost } from "./client";
import type { Paginated } from "../types/common";
import type {
  OrderCreate,
  OrderListItem,
  OrderListParams,
  OrderResponse,
} from "../types/order";
import type { PaymentRequest, PaymentResponse } from "../types/payment";

export function createOrder(
  data: OrderCreate,
  idempotencyKey?: string
): Promise<OrderResponse> {
  return apiPost<OrderResponse>("/api/v1/orders", data, {
    headers: idempotencyKey
      ? { "Idempotency-Key": idempotencyKey }
      : undefined,
  });
}

export function listOrders(
  params: OrderListParams = {}
): Promise<Paginated<OrderListItem>> {
  return apiGet<Paginated<OrderListItem>>("/api/v1/orders", params);
}

export function fetchOrder(publicId: string): Promise<OrderResponse> {
  return apiGet<OrderResponse>(`/api/v1/orders/${publicId}`);
}

export function payOrder(
  publicId: string,
  data: PaymentRequest
): Promise<PaymentResponse> {
  return apiPost<PaymentResponse>(
    `/api/v1/orders/${publicId}/pay`,
    data
  );
}
