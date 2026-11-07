// frontend/src/context/FavoritesProvider.tsx
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import {
  addFavorite as addFavoriteRequest,
  fetchFavorites,
  removeFavorite as removeFavoriteRequest,
} from "../api/favorites";
import { FavoritesContext } from "./favoritesContext";
import type { FavoritesContextValue } from "./favoritesContext";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errors";
import type { FavoriteResponse } from "../types/favorite";

interface Props {
  children: ReactNode;
}

export function FavoritesProvider({ children }: Props) {
  const { user, loading: authLoading } = useAuth();
  const userId = user?.public_id ?? null;
  const [favorites, setFavorites] = useState<FavoriteResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<number[]>([]);

  useEffect(() => {
    if (authLoading) return;

    if (userId === null) {
      setFavorites([]);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchFavorites()
      .then((data) => {
        if (!cancelled) setFavorites(data);
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
  }, [authLoading, userId]);

  const refreshFavorites = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFavorites();
      setFavorites(data);
    } catch (err) {
      setError(getErrorMessage(err));
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const isFavorite = useCallback(
    (productId: number) =>
      favorites.some((item) => item.product_id === productId),
    [favorites]
  );

  const isPending = useCallback(
    (productId: number) => pendingIds.includes(productId),
    [pendingIds]
  );

  const toggleFavorite = useCallback(
    async (productId: number) => {
      if (user === null) {
        throw new Error("Требуется авторизация");
      }
      if (pendingIds.includes(productId)) {
        return;
      }

      const existing = favorites.find(
        (item) => item.product_id === productId
      );

      setPendingIds((prev) => [...prev, productId]);

      try {
        if (existing !== undefined) {
          // Удаление оптимистично: сразу убираем из UI, откатываем при ошибке.
          setFavorites((prev) =>
            prev.filter((item) => item.product_id !== productId)
          );
          try {
            await removeFavoriteRequest(productId);
          } catch (err) {
            setFavorites((prev) => [existing, ...prev]);
            throw err;
          }
        } else {
          // Добавление ждёт ответ, потому что FavoriteResponse содержит
          // name/cost/status из БД — конструировать их локально нельзя.
          const created = await addFavoriteRequest({ product_id: productId });
          setFavorites((prev) =>
            prev.some((item) => item.product_id === productId)
              ? prev
              : [created, ...prev]
          );
        }
      } finally {
        setPendingIds((prev) =>
          prev.filter((id) => id !== productId)
        );
      }
    },
    [favorites, pendingIds, user]
  );

  const value = useMemo<FavoritesContextValue>(
    () => ({
      favorites,
      loading,
      error,
      refreshFavorites,
      isFavorite,
      isPending,
      toggleFavorite,
    }),
    [
      favorites,
      loading,
      error,
      refreshFavorites,
      isFavorite,
      isPending,
      toggleFavorite,
    ]
  );

  return (
    <FavoritesContext.Provider value={value}>
      {children}
    </FavoritesContext.Provider>
  );
}
