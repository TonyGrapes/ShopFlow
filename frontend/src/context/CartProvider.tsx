// frontend/src/context/CartProvider.tsx
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import {
  addCartItem as addCartItemRequest,
  applyPromo as applyPromoRequest,
  clearCart as clearCartRequest,
  fetchCart,
  removeCartItem,
  updateCartItem,
} from "../api/cart";
import { CartContext } from "./cartContext";
import type { CartContextValue } from "./cartContext";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errors";
import type { CartResponse } from "../types/cart";
import type { PromoCodePreviewResponse } from "../types/promo";

interface Props {
  children: ReactNode;
}

export function CartProvider({ children }: Props) {
  const { user, loading: authLoading } = useAuth();
  const [cart, setCart] = useState<CartResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Перезагружаем корзину при смене владельца:
  // гость → пользователь (бэкенд уже смержил корзины при login)
  // и пользователь → гость (после logout).
  useEffect(() => {
    if (authLoading) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchCart()
      .then((data) => {
        if (!cancelled) setCart(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [authLoading, user?.public_id]);

  const refreshCart = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCart();
      setCart(data);
    } catch (err) {
      setError(getErrorMessage(err));
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const addItem = useCallback(
    async (productId: number, quantity = 1) => {
      const data = await addCartItemRequest({
        product_id: productId,
        quantity,
      });
      setCart(data);
      return data;
    },
    []
  );

  const updateItem = useCallback(
    async (productId: number, quantity: number) => {
      const data = await updateCartItem(productId, { quantity });
      setCart(data);
      return data;
    },
    []
  );

  const removeItem = useCallback(async (productId: number) => {
    const data = await removeCartItem(productId);
    setCart(data);
    return data;
  }, []);

  const clearCart = useCallback(async () => {
    await clearCartRequest();
    const data = await fetchCart();
    setCart(data);
  }, []);

  const applyPromo = useCallback(
    (code: string): Promise<PromoCodePreviewResponse> => {
      return applyPromoRequest({ code });
    },
    []
  );

  const value = useMemo<CartContextValue>(
    () => ({
      cart,
      loading,
      error,
      totalItems: cart?.total_items ?? 0,
      refreshCart,
      addItem,
      updateItem,
      removeItem,
      clearCart,
      applyPromo,
    }),
    [
      cart,
      loading,
      error,
      refreshCart,
      addItem,
      updateItem,
      removeItem,
      clearCart,
      applyPromo,
    ]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}
