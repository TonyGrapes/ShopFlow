import { describe, expect, it } from "vitest";

import { STATUS_LABELS, STATUS_TONES } from "./status";

describe("catalog status maps", () => {
  it("содержит подписи для всех статусов", () => {
    expect(STATUS_LABELS).toEqual({
      available: "В наличии",
      out_of_stock: "Нет в наличии",
      discontinued: "Снят с производства",
    });
  });

  it("содержит тон для всех статусов", () => {
    expect(STATUS_TONES).toEqual({
      available: "success",
      out_of_stock: "warning",
      discontinued: "muted",
    });
  });
});
