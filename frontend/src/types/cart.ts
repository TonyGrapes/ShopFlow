// frontend/src/types/cart.ts
/**
 * Типы, синхронные с backend app/schemas/cart.py.
 *
 * Бэкенд различает гостя (Redis + cookie) и пользователя (PostgreSQL),
 * но контракт ответа для обоих одинаковый — CartResponse.
 */
import type { Money } from "./common";
import type { ProductStatus } from "./product";

// app/schemas/cart.py — CartItemCreate
export interface CartItemCreate {
  product_id: number;
  quantity: number;
}

// app/schemas/cart.py — CartItemUpdate
// quantity = 0 удаляет позицию.
export interface CartItemUpdate {
  quantity: number;
}

// app/schemas/cart.py — CartItemResponse
export interface CartItemResponse {
  product_id: number;
  name: string;
  cover_url: string | null;
  quantity: number;
  snapshot_cost: Money;
  current_cost: Money;
  status: ProductStatus;
  is_available: boolean;
}

// app/schemas/cart.py — CartResponse
export interface CartResponse {
  items: CartItemResponse[];
  total_items: number;
  total_cost: Money;
  hidden_items_count: number;
}
