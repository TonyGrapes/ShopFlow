import { describe, it, expect } from "vitest";
import {
  isValidEmail,
  isValidPassword,
  isValidPhone,
} from "./validation";

describe("validation", () => {
  it("isValidEmail", () => {
    expect(isValidEmail("a@b.co")).toBe(true);
    expect(isValidEmail("not-email")).toBe(false);
  });

  it("isValidPassword (8..128)", () => {
    expect(isValidPassword("1234567")).toBe(false);
    expect(isValidPassword("12345678")).toBe(true);
    expect(isValidPassword("x".repeat(129))).toBe(false);
  });

  it("isValidPhone", () => {
    expect(isValidPhone("+7 999 000-00-00")).toBe(true);
    expect(isValidPhone("abc")).toBe(false);
  });
});