// frontend/src/types/index.ts
/**
 * Barrel-экспорт доменных типов.
 *
 * Money и Paginated экспортируются через product.ts — common.ts
 * отдельно не реэкспортируется, чтобы не было конфликта имён.
 */
export type * from "./address";
export type * from "./auth";
export type * from "./cart";
export type * from "./category";
export type * from "./favorite";
export type * from "./order";
export type * from "./payment";
export type * from "./product";
export type * from "./promo";
