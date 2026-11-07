import type { ProductStatus } from "../../../types/product";
import { productStatusLabel } from "../../../utils/labels";

export const STATUS_LABELS: Record<ProductStatus, string> = {
  available: productStatusLabel("available"),
  out_of_stock: productStatusLabel("out_of_stock"),
  discontinued: productStatusLabel("discontinued"),
};

export type StatusTone = "success" | "warning" | "muted";

export const STATUS_TONES: Record<ProductStatus, StatusTone> = {
  available: "success",
  out_of_stock: "warning",
  discontinued: "muted",
};
