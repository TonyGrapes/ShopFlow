import { describe, it, expect } from "vitest";
import { formatMoney, formatDate } from "./format";

describe("formatMoney", () => {
  it("форматирует строковое Money", () => {
    expect(formatMoney("1999.99")).toMatch(/1\s*999,99\s*₽/);
  });

  it("возвращает оригинал при невалидном значении", () => {
    expect(formatMoney("not-a-number")).toBe("not-a-number ₽");
  });
});

describe("formatDate", () => {
  it("возвращает невалидную дату как есть", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });
});