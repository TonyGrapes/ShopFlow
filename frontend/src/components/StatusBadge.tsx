// frontend/src/components/StatusBadge.tsx
import type { OrderStatus } from "../types/order";
import type { PaymentStatus } from "../types/payment";
import type { ProductStatus } from "../types/product";
import {
  orderStatusLabel,
  paymentStatusLabel,
  productStatusLabel,
} from "../utils/labels";

type Props =
  | { kind: "order"; status: OrderStatus }
  | { kind: "payment"; status: PaymentStatus }
  | { kind: "product"; status: ProductStatus };

export function StatusBadge(props: Props) {
  let label: string;

  switch (props.kind) {
    case "order":
      label = orderStatusLabel(props.status);
      break;
    case "payment":
      label = paymentStatusLabel(props.status);
      break;
    case "product":
      label = productStatusLabel(props.status);
      break;
  }

  return (
    <span className={`badge badge--${props.status}`}>{label}</span>
  );
}
