import type { ReactNode } from "react";
import { AuthProvider } from "../context/AuthProvider";
import { CartProvider } from "../context/CartProvider";
import { FavoritesProvider } from "../context/FavoritesProvider";
import { ToastProvider } from "../context/ToastProvider";

interface Props {
  children: ReactNode;
}

export function AppProviders({ children }: Props) {
  return (
    <ToastProvider>
      <AuthProvider>
        <FavoritesProvider>
          <CartProvider>{children}</CartProvider>
        </FavoritesProvider>
      </AuthProvider>
    </ToastProvider>
  );
}
