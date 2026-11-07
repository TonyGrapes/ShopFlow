// frontend/src/components/FavoriteButton.tsx
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useFavorites } from "../hooks/useFavorites";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";

interface Props {
  productId: number;
  className?: string;
}

export function FavoriteButton({ productId, className }: Props) {
  const { user } = useAuth();
  const { isFavorite, isPending, toggleFavorite } = useFavorites();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const favorite = isFavorite(productId);
  const pending = isPending(productId);

  async function handleClick() {
    if (user === null) {
      const from = window.location.pathname + window.location.search;
      showToast("Войдите, чтобы добавить товар в избранное", "info");
      navigate("/login", { state: { from } });
      return;
    }

    try {
      await toggleFavorite(productId);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    }
  }

  const classes = [
    "btn",
    "btn--secondary",
    "btn--sm",
    favorite ? "favorite-button favorite-button--active" : "favorite-button",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type="button"
      className={classes}
      onClick={handleClick}
      disabled={pending}
      aria-pressed={favorite}
    >
      {pending ? "..." : favorite ? "В избранном" : "В избранное"}
    </button>
  );
}
