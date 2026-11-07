// frontend/src/components/AddToCartButton.tsx
import { useState } from "react";
import { useCart } from "../hooks/useCart";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";

interface Props {
  productId: number;
  available: boolean;
  className?: string;
}

export function AddToCartButton({ productId, available, className }: Props) {
  const { addItem } = useCart();
  const { showToast } = useToast();
  const [pending, setPending] = useState(false);

  async function handleClick() {
    if (!available || pending) return;

    setPending(true);
    try {
      const cart = await addItem(productId, 1);
      showToast(`Товар добавлен. В корзине: ${cart.total_items}`, "success");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  const classes = className ?? "btn btn--primary btn--sm";

  return (
    <button
      type="button"
      className={classes}
      onClick={handleClick}
      disabled={!available || pending}
    >
      {!available ? "Нет в наличии" : pending ? "Добавляем..." : "В корзину"}
    </button>
  );
}
