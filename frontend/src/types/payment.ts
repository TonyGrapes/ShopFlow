// frontend/src/types/payment.ts
/**
 * Типы, синхронные с backend app/schemas/payment.py и app/db/enum.py.
 */
import type { Money } from "./common";

// app/db/enum.py — PaymentMethod
export type PaymentMethod = "card" | "bank_transfer" | "crypto" | "cash";

// app/db/enum.py — PaymentStatus
export type PaymentStatus = "pending" | "completed" | "failed" | "refunded";

// app/schemas/payment.py — PaymentRequest
export interface PaymentRequest {
  external_id?: string | null;
  method: PaymentMethod;
}

// app/schemas/payment.py — PaymentResponse
export interface PaymentResponse {
  public_id: string;
  status: PaymentStatus;
  amount: Money;
  currency: string;
  method: PaymentMethod;
  external_id: string | null;
  paid_at: string | null;
  created_at: string;
}
