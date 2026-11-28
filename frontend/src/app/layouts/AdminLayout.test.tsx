import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { AdminLayout } from "./AdminLayout";
import { renderWithProviders } from "../../test/render";
import type { UserResponse } from "../../types/auth";

const USER: UserResponse = {
  public_id: "u-1",
  email: "admin@example.com",
  first_name: "Admin",
  last_name: "Root",
  phone_number: "+10000000000",
  role: "admin",
  status: "active",
  is_email_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

function renderLayout(
  route = "/admin",
  options: {
    logout?: () => Promise<void>;
    toasts?: { id: number; message: string; type: "success" | "error" | "info" }[];
    removeToast?: (id: number) => void;
  } = {}
) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<div>dashboard content</div>} />
        <Route path="orders" element={<div>orders content</div>} />
      </Route>
    </Routes>,
    {
      route,
      auth: { user: USER, logout: options.logout ?? (async () => {}) },
      toast: {
        toasts: options.toasts ?? [],
        removeToast: options.removeToast ?? (() => {}),
      },
    }
  );
}

describe("AdminLayout", () => {
  it("рендерит бренд, навигацию, пользователя и outlet", () => {
    renderLayout();

    expect(screen.getByRole("link", { name: /ShopFlow Admin/ })).toHaveAttribute(
      "href",
      "/admin"
    );
    const nav = screen.getByRole("navigation", { name: "Админ-навигация" });
    expect(within(nav).getByRole("link", { name: "Обзор" })).toHaveAttribute(
      "href",
      "/admin"
    );
    expect(
      within(nav).getByRole("link", { name: "Заказы" })
    ).toHaveAttribute("href", "/admin/orders");
    expect(
      within(nav).getByRole("link", { name: "Категории" })
    ).toHaveAttribute("href", "/admin/categories");
    expect(
      within(nav).getByRole("link", { name: "Товары" })
    ).toHaveAttribute("href", "/admin/products");
    expect(
      within(nav).getByRole("link", { name: "Пользователи" })
    ).toHaveAttribute("href", "/admin/users");

    expect(within(nav).getByRole("link", { name: "Обзор" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(screen.getByText("dashboard content")).toBeInTheDocument();
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "В магазин" })).toHaveAttribute(
      "href",
      "/"
    );
  });

  it("активный пункт меняется на вложенном роуте", () => {
    renderLayout("/admin/orders");

    const nav = screen.getByRole("navigation", { name: "Админ-навигация" });
    expect(within(nav).getByRole("link", { name: "Заказы" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(
      within(nav).getByRole("link", { name: "Обзор" })
    ).not.toHaveAttribute("aria-current");
    expect(screen.getByText("orders content")).toBeInTheDocument();
  });

  it("кнопка «Выйти» вызывает logout", async () => {
    const user = userEvent.setup();
    const logout = vi.fn().mockResolvedValue(undefined);
    renderLayout("/admin", { logout });

    await user.click(screen.getByRole("button", { name: "Выйти" }));

    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("ToastContainer показывает уведомление и закрывает его", async () => {
    const user = userEvent.setup();
    const removeToast = vi.fn();
    renderLayout("/admin", {
      toasts: [{ id: 5, message: "Товар создан", type: "success" }],
      removeToast,
    });

    expect(screen.getByRole("status")).toHaveTextContent("Товар создан");
    await user.click(
      screen.getByRole("button", { name: "Закрыть уведомление" })
    );

    expect(removeToast).toHaveBeenCalledWith(5);
  });
});
