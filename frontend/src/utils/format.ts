// frontend/src/utils/format.ts
import type { Money } from "../types/common";

/**
 * Money приходит с бэкенда строкой ("1999.99").
 * Для отображения используем Intl.NumberFormat.
 */
export function formatMoney(value: Money): string {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return `${value} ₽`;
  }
  return `${num.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ₽`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
