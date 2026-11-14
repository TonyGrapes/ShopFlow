import { describe, it, expect } from "vitest";
import { getErrorMessage } from "./errors";
import { ApiError } from "../api/client";

describe("getErrorMessage", () => {
  it("ApiError → detail", () => {
    expect(getErrorMessage(new ApiError(400, "Bad Request"))).toBe(
      "Bad Request"
    );
  });

  it("обычная Error → message", () => {
    expect(getErrorMessage(new Error("boom"))).toBe("boom");
  });

  it("неизвестное → generic", () => {
    expect(getErrorMessage(42)).toBe("Неизвестная ошибка");
  });
});