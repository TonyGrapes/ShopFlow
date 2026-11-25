import { describe, expect, it } from "vitest";

import {
  formatPrice,
  formatProductCount,
  pluralize,
} from "./format";

describe("formatPrice", () => {
  it("форматирует число в рубли без копеек", () => {
    expect(formatPrice(1234)).toMatch(/1\s*234\s*₽/);
  });

  it("принимает строку Money", () => {
    expect(formatPrice("1000")).toMatch(/1\s*000\s*₽/);
  });

  it("нечисловое значение → 0 ₽", () => {
    expect(formatPrice("not-a-number")).toMatch(/0\s*₽/);
  });
});

describe("pluralize", () => {
  const forms: [number, string][] = [
    [1, "товар"],
    [21, "товар"],
    [101, "товар"],
    [2, "товара"],
    [3, "товара"],
    [4, "товара"],
    [22, "товара"],
    [5, "товаров"],
    [11, "товаров"],
    [12, "товаров"],
    [14, "товаров"],
    [0, "товаров"],
  ];

  it.each(forms)("%i → %s", (count, expected) => {
    expect(pluralize(count, "товар", "товара", "товаров")).toBe(expected);
  });
});

describe("formatProductCount", () => {
  it("согласует число и слово", () => {
    expect(formatProductCount(1)).toBe("1 товар");
    expect(formatProductCount(3)).toBe("3 товара");
    expect(formatProductCount(5)).toBe("5 товаров");
  });
});
