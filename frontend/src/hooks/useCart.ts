// frontend/src/hooks/useCart.ts
import { useContext } from "react";
import { CartContext } from "../context/cartContext";

export function useCart() {
  const context = useContext(CartContext);
  if (context === null) {
    throw new Error("useCart must be used within CartProvider");
  }
  return context;
}
