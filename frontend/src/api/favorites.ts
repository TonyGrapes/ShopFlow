// frontend/src/api/favorites.ts
/**
 * Favorites API. Требует авторизации.
 */
import { apiDelete, apiGet, apiPost } from "./client";
import type {
  FavoriteCreate,
  FavoriteResponse,
} from "../types/favorite";

export function fetchFavorites(): Promise<FavoriteResponse[]> {
  return apiGet<FavoriteResponse[]>("/api/v1/favorites");
}

export function addFavorite(
  data: FavoriteCreate
): Promise<FavoriteResponse> {
  return apiPost<FavoriteResponse>("/api/v1/favorites", data);
}

export function removeFavorite(productId: number): Promise<void> {
  return apiDelete<void>(`/api/v1/favorites/${productId}`);
}
