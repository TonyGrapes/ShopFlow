// frontend/src/types/promo.ts
/**
 * Типы, синхронные с backend app/schemas/promo.py и app/db/enum.py.
 */
import type { Money } from "./common";

// app/db/enum.py — DiscountType
export type DiscountType = "percentage" | "fixed" | "free_shipping";

// app/schemas/promo.py — PromoCodePreviewRequest
export interface PromoCodePreviewRequest {
  code: string;
}

// app/schemas/promo.py — PromoCodePreviewResponse
export interface PromoCodePreviewResponse {
  code: string;
  discount_type: DiscountType;
  discount_value: Money;
  subtotal: Money;
  discount_amount: Money;
  final_total: Money;
}
