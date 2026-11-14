import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";

import { Header } from "./Header";
import { renderWithProviders } from "../test/render";

describe("Header", () => {
  it("гость видит «Войти» и «Регистрация»", () => {
    renderWithProviders(<Header />);
    expect(screen.getByRole("link", { name: "Войти" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Регистрация" })
    ).toBeInTheDocument();
  });

  it("залогиненный видит «Профиль» и «Заказы»", () => {
    renderWithProviders(<Header />, {
      auth: {
        user: {
          public_id: "u-1",
          email: "user@example.com",
          first_name: "Test",
          last_name: "User",
          phone_number: "+79990000001",
          role: "customer",
          status: "active",
          is_email_verified: true,
          created_at: "2026-01-01T00:00:00Z",
        },
        isAuthenticated: true,
      },
    });
    expect(screen.getByRole("link", { name: "Профиль" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Заказы" })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Админка" })
    ).not.toBeInTheDocument();
  });

  it("admin видит «Админка»", () => {
    renderWithProviders(<Header />, {
      auth: {
        user: {
          public_id: "u-2",
          email: "admin@example.com",
          first_name: "Admin",
          last_name: "User",
          phone_number: "+79990000002",
          role: "admin",
          status: "active",
          is_email_verified: true,
          created_at: "2026-01-01T00:00:00Z",
        },
        isAuthenticated: true,
      },
    });
    expect(screen.getByRole("link", { name: "Админка" })).toBeInTheDocument();
  });
});