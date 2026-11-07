// frontend/src/context/cartContext.ts
import { createContext } from "react";
import type { CartResponse } from "../types/cart";
import type { PromoCodePreviewResponse } from "../types/promo";

export interface CartContextValue {
  cart: CartResponse | null;
  loading: boolean;
  error: string | null;
  totalItems: number;
  refreshCart: () => Promise<void>;
  addItem: (productId: number, quantity?: number) => Promise<CartResponse>;
  updateItem: (productId: number, quantity: number) => Promise<CartResponse>;
  removeItem: (productId: number) => Promise<CartResponse>;
  clearCart: () => Promise<void>;
  applyPromo: (code: string) => Promise<PromoCodePreviewResponse>;
}

export const CartContext = createContext<CartContextValue | null>(null);
