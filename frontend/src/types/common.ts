// frontend/src/types/common.ts
/**
 * Общие типы, синхронные с backend app/schemas/common.py.
 *
 * Money — Decimal на бэкенде, в JSON приходит строкой ("1999.99").
 * Paginated[T] — универсальная обёртка пагинации.
 */

export type Money = string;

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
