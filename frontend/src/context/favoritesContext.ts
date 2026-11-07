// frontend/src/context/favoritesContext.ts
import { createContext } from "react";
import type { FavoriteResponse } from "../types/favorite";

export interface FavoritesContextValue {
  favorites: FavoriteResponse[];
  loading: boolean;
  error: string | null;
  refreshFavorites: () => Promise<void>;
  isFavorite: (productId: number) => boolean;
  isPending: (productId: number) => boolean;
  toggleFavorite: (productId: number) => Promise<void>;
}

export const FavoritesContext =
  createContext<FavoritesContextValue | null>(null);
