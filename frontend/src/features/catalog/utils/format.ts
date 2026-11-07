import type { Money } from "../../../types/common";

const priceFormatter = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

export function formatPrice(value: Money | number): string {
  const numeric = typeof value === "number" ? value : Number(value);
  return priceFormatter.format(Number.isFinite(numeric) ? numeric : 0);
}

export function pluralize(
  count: number,
  one: string,
  few: string,
  many: string
): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export function formatProductCount(count: number): string {
  return `${count} ${pluralize(count, "товар", "товара", "товаров")}`;
}
