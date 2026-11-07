// frontend/src/utils/labels.ts
import type { OrderStatus } from "../types/order";
import type { PaymentMethod, PaymentStatus } from "../types/payment";
import type { ProductStatus } from "../types/product";

export function productStatusLabel(status: ProductStatus): string {
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

export function orderStatusLabel(status: OrderStatus): string {
  switch (status) {
    case "pending":
      return "Ожидает оплаты";
    case "paid":
      return "Оплачен";
    case "shipped":
      return "Отправлен";
    case "delivered":
      return "Доставлен";
    case "canceled":
      return "Отменён";
    default:
      return status;
  }
}

export function paymentStatusLabel(status: PaymentStatus): string {
  switch (status) {
    case "pending":
      return "Ожидает";
    case "completed":
      return "Завершён";
    case "failed":
      return "Ошибка";
    case "refunded":
      return "Возврат";
    default:
      return status;
  }
}

export function paymentMethodLabel(method: PaymentMethod): string {
  switch (method) {
    case "card":
      return "Банковская карта";
    case "bank_transfer":
      return "Банковский перевод";
    case "crypto":
      return "Криптовалюта";
    case "cash":
      return "Наличные";
    default:
      return method;
  }
}
