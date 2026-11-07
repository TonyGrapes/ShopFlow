// frontend/src/pages/FavoritesPage.tsx
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useFavorites } from "../hooks/useFavorites";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import { formatMoney } from "../utils/format";

function favoriteStatusLabel(status: string): string {
  switch (status) {
    case "available":
      return "В наличии";
    case "out_of_stock":
      return "Нет в наличии";
    case "discontinued":
      return "Снят с производства";
    default:
      return status;
  }
}

export function FavoritesPage() {
  const {
    favorites,
    loading,
    error,
    refreshFavorites,
    toggleFavorite,
    isPending,
  } = useFavorites();
  const { showToast } = useToast();

  async function handleRemove(productId: number) {
    try {
      await toggleFavorite(productId);
      showToast("Товар удалён из избранного", "info");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    }
  }

  return (
    <div className="favorites-page">
      <div className="page-heading">
        <h1>Избранное</h1>
        <Link to="/">← В каталог</Link>
      </div>

      {loading && favorites.length === 0 && <LoadingState />}

      {error !== null && (
        <ErrorState
          message={error}
          onRetry={() => {
            void refreshFavorites().catch(() => undefined);
          }}
        />
      )}

      {!loading && error === null && favorites.length === 0 && (
        <EmptyState message="В избранном пока ничего нет" />
      )}

      {favorites.length > 0 && (
        <div className="favorites-list">
          {favorites.map((favorite) => {
            const pending = isPending(favorite.product_id);
            return (
              <div className="favorite-card" key={favorite.id}>
                <div className="favorite-card__cover">
                  {favorite.cover_url !== null ? (
                    <img
                      src={favorite.cover_url}
                      alt={favorite.product_name}
                    />
                  ) : (
                    <div className="cart-item__no-cover">
                      Нет изображения
                    </div>
                  )}
                </div>

                <div className="favorite-card__body">
                  <Link
                    to={`/products/${favorite.product_id}`}
                    className="favorite-card__name"
                  >
                    {favorite.product_name}
                  </Link>
                  <p className="favorite-card__cost">
                    {formatMoney(favorite.cost)}
                  </p>
                  <p className="muted">
                    {favoriteStatusLabel(favorite.status)}
                  </p>
                </div>

                <button
                  type="button"
                  className="btn btn--danger btn--sm"
                  onClick={() => void handleRemove(favorite.product_id)}
                  disabled={pending}
                >
                  {pending ? "..." : "Удалить"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
