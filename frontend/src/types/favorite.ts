// frontend/src/types/favorite.ts
/**
 * Типы, синхронные с backend app/schemas/favorite.py.
 *
 * Обратите внимание: status здесь — обычная строка (на бэкенде str),
 * а не ProductStatus. Не сужаем тип, чтобы не разойтись со схемой.
 */
import type { Money } from "./common";

// app/schemas/favorite.py — FavoriteCreate
export interface FavoriteCreate {
  product_id: number;
}

// app/schemas/favorite.py — FavoriteResponse
export interface FavoriteResponse {
  id: number;
  product_id: number;
  product_name: string;
  cover_url: string | null;
  cost: Money;
  status: string;
  created_at: string;
}
