import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AdminDashboardPage } from "./AdminDashboardPage";
import { renderWithProviders } from "../../../test/render";

vi.mock("../../../api/admin", () => ({
  fetchAdminDashboard: vi.fn(),
  fetchAdminDashboardSeries: vi.fn(),
  downloadDashboardCsv: vi.fn(),
}));

import {
  fetchAdminDashboard,
  fetchAdminDashboardSeries,
} from "../../../api/admin";

const mockFetchDashboard = vi.mocked(fetchAdminDashboard);
const mockFetchSeries = vi.mocked(fetchAdminDashboardSeries);

const emptyDashboard = {
  period_days: 7,
  orders_count: 0,
  revenue_gross: "0.00",
  refunds_total: "0.00",
  revenue_net: "0.00",
  new_users_count: 0,
  top_products: [],
  orders_count_prev: 0,
  orders_count_delta_pct: null,
  revenue_gross_prev: "0.00",
  revenue_gross_delta_pct: null,
  refunds_total_prev: "0.00",
  refunds_total_delta_pct: null,
  new_users_count_prev: 0,
  new_users_count_delta_pct: null,
};

describe("AdminDashboardPage", () => {
  beforeEach(() => {
    mockFetchDashboard.mockReset();
    mockFetchSeries.mockReset();
  });

  it("рендерится без падений (rules-of-hooks)", async () => {
    mockFetchDashboard.mockResolvedValue(emptyDashboard);
    mockFetchSeries.mockResolvedValue({ period_days: 7, items: [] });

    renderWithProviders(<AdminDashboardPage />);

    // Если useToast() вызван вне компонента — тест упадёт здесь
    // с "Invalid hook call", ещё до waitFor.
    expect(await screen.findByRole("heading", { name: "Обзор" }))
      .toBeInTheDocument();
  });

  it("показывает метрики из ответа API", async () => {
    mockFetchDashboard.mockResolvedValue({
      ...emptyDashboard,
      orders_count: 5,
      revenue_gross: "1234.00",
      revenue_net: "1000.00",
      new_users_count: 3,
      top_products: [
        {
          product_id: 1,
          product_name: "Laptop",
          total_quantity: 2,
          total_revenue: "1000.00",
        },
      ],
    });
    mockFetchSeries.mockResolvedValue({ period_days: 7, items: [] });

    renderWithProviders(<AdminDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText("Laptop")).toBeInTheDocument();
    });
  });

  it("кнопка «Скачать CSV» присутствует", async () => {
    mockFetchDashboard.mockResolvedValue(emptyDashboard);
    mockFetchSeries.mockResolvedValue({ period_days: 7, items: [] });

    renderWithProviders(<AdminDashboardPage />);

    expect(
      await screen.findByRole("button", { name: /Скачать CSV/i })
    ).toBeInTheDocument();
  });
});