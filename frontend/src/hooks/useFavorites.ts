// frontend/src/hooks/useFavorites.ts
import { useContext } from "react";
import { FavoritesContext } from "../context/favoritesContext";

export function useFavorites() {
  const context = useContext(FavoritesContext);
  if (context === null) {
    throw new Error("useFavorites must be used within FavoritesProvider");
  }
  return context;
}
