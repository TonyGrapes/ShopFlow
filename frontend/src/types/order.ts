// frontend/src/types/order.ts
/**
 * Типы, синхронные с backend app/schemas/order.py и app/db/enum.py.
 *
 * Публичный идентификатор заказа — public_id (UUID в виде строки).
 */
import type { AddressBrief } from "./address";
import type { Money } from "./common";
import type { PaymentResponse } from "./payment";
import type { ProductStatus } from "./product";

// app/db/enum.py — OrderStatus
export type OrderStatus =
  | "pending"
  | "paid"
  | "shipped"
  | "delivered"
  | "canceled";

// app/schemas/order.py — OrderCreate
export interface OrderCreate {
  address_id: number;
  promo_code?: string | null;
}

// app/schemas/order.py — OrderItemProductBrief
export interface OrderItemProductBrief {
  id: number;
  name: string;
  cover_url: string | null;
  status: ProductStatus;
}

// app/schemas/order.py — OrderItemResponse
export interface OrderItemResponse {
  public_id: string;
  product: OrderItemProductBrief;
  product_cost: Money;
  product_count: number;
  created_at: string;
}

// app/schemas/order.py — OrderResponse
export interface OrderResponse {
  public_id: string;
  status: OrderStatus;
  subtotal: Money;
  discount_amount: Money | null;
  total: Money;
  promo_code: string | null;
  shipping_address: AddressBrief;
  items: OrderItemResponse[];
  payments: PaymentResponse[];
  created_at: string;
  updated_at: string;
}

// app/schemas/order.py — OrderListItem
export interface OrderListItem {
  public_id: string;
  status: OrderStatus;
  discount_amount: Money | null;
  total: Money;
  items_count: number;
  created_at: string;
}

// Query-параметры GET /api/v1/orders
export interface OrderListParams {
  page?: number;
  page_size?: number;
  status?: OrderStatus;
}
