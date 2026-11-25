// renderWithProviders — обёртка для тестов.
//
// НЕ используем реальные AuthProvider/CartProvider/FavoritesProvider:
// они при mount делают bootstrap (refreshAccessToken, fetchCart,
// fetchFavorites) → потребовали бы мокать api/session, api/cart,
// api/favorites в каждом тесте. Вместо этого подменяем значения
// контекстов напрямую через .Provider — компоненты получают хуки
// (useAuth, useCart, useFavorites, useToast), но без side-effects.
import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import type { RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AuthContext } from "../context/authContext";
import type { AuthContextValue } from "../context/authContext";
import { CartContext } from "../context/cartContext";
import type { CartContextValue } from "../context/cartContext";
import {
  FavoritesContext,
} from "../context/favoritesContext";
import type { FavoritesContextValue } from "../context/favoritesContext";
import { ToastContext } from "../context/toastContext";
import type { ToastContextValue } from "../context/toastContext";

import type { CartResponse } from "../types/cart";

const emptyCart: CartResponse = {
  items: [],
  total_items: 0,
  total_cost: "0.00",
  hidden_items_count: 0,
};

export function mockAuth(
  overrides: Partial<AuthContextValue> = {}
): AuthContextValue {
  return {
    user: null,
    loading: false,
    isAuthenticated: false,
    login: async () => {},
    register: async () => {
      throw new Error("not used in tests");
    },
    logout: async () => {},
    refreshUser: async () => {},
    ...overrides,
  };
}

export function mockCart(
  overrides: Partial<CartContextValue> = {}
): CartContextValue {
  return {
    cart: emptyCart,
    loading: false,
    error: null,
    totalItems: 0,
    refreshCart: async () => {},
    addItem: async () => emptyCart,
    updateItem: async () => emptyCart,
    removeItem: async () => emptyCart,
    clearCart: async () => {},
    applyPromo: async () => {
      throw new Error("not used in tests");
    },
    ...overrides,
  };
}

export function mockFavorites(
  overrides: Partial<FavoritesContextValue> = {}
): FavoritesContextValue {
  return {
    favorites: [],
    loading: false,
    error: null,
    refreshFavorites: async () => {},
    isFavorite: () => false,
    isPending: () => false,
    toggleFavorite: async () => {},
    ...overrides,
  };
}

export function mockToast(
  overrides: Partial<ToastContextValue> = {}
): ToastContextValue {
  return {
    toasts: [],
    showToast: () => {},
    removeToast: () => {},
    ...overrides,
  };
}

interface Options extends Omit<RenderOptions, "wrapper"> {
  auth?: Partial<AuthContextValue>;
  cart?: Partial<CartContextValue>;
  favorites?: Partial<FavoritesContextValue>;
  toast?: Partial<ToastContextValue>;
  route?: string;
  routeState?: unknown;
}

export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const {
    auth,
    cart,
    favorites,
    toast,
    route = "/",
    routeState,
    ...rest
  } = options;

  return render(
    <MemoryRouter initialEntries={[{ pathname: route, state: routeState }]}>
      <ToastContext.Provider value={mockToast(toast)}>
        <AuthContext.Provider value={mockAuth(auth)}>
          <FavoritesContext.Provider value={mockFavorites(favorites)}>
            <CartContext.Provider value={mockCart(cart)}>
              {ui}
            </CartContext.Provider>
          </FavoritesContext.Provider>
        </AuthContext.Provider>
      </ToastContext.Provider>
    </MemoryRouter>,
    rest
  );
}