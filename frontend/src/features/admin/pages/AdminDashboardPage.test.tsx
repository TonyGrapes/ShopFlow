import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdminDashboardPage } from "./AdminDashboardPage";
import { RevenueChart } from "../components/RevenueChart";
import { renderWithProviders } from "../../../test/render";
import type {
  AdminDashboardResponse,
  AdminDashboardSeriesResponse,
  DailySeriesItem,
} from "../../../types/admin";

vi.mock("../../../api/admin", () => ({
  fetchAdminDashboard: vi.fn(),
  fetchAdminDashboardSeries: vi.fn(),
  downloadDashboardCsv: vi.fn(),
}));

import {
  downloadDashboardCsv,
  fetchAdminDashboard,
  fetchAdminDashboardSeries,
} from "../../../api/admin";

const mDash = vi.mocked(fetchAdminDashboard);
const mSeries = vi.mocked(fetchAdminDashboardSeries);
const mCsv = vi.mocked(downloadDashboardCsv);

const DASH: AdminDashboardResponse = {
  period_days: 7,
  orders_count: 10,
  revenue_gross: "10000.00",
  refunds_total: "500.00",
  revenue_net: "9500.00",
  new_users_count: 3,
  top_products: [
    {
      product_id: 1,
      product_name: "Laptop",
      total_quantity: 2,
      total_revenue: "5000.00",
    },
  ],
  orders_count_prev: 8,
  orders_count_delta_pct: 25,
  revenue_gross_prev: "9000.00",
  revenue_gross_delta_pct: 10.5,
  refunds_total_prev: "600.00",
  refunds_total_delta_pct: null,
  new_users_count_prev: 4,
  new_users_count_delta_pct: -5,
};

const SERIES: AdminDashboardSeriesResponse = {
  period_days: 7,
  items: [
    { date: "2026-01-01", orders_count: 2, revenue_gross: "1000.00" },
    { date: "2026-01-02", orders_count: 3, revenue_gross: "2000.00" },
  ],
};

function renderPage(showToast = vi.fn()) {
  return renderWithProviders(<AdminDashboardPage />, {
    toast: { showToast },
  });
}

beforeEach(() => {
  mDash.mockReset().mockResolvedValue(DASH);
  mSeries.mockReset().mockResolvedValue(SERIES);
  mCsv.mockReset().mockResolvedValue(undefined);
});

describe("AdminDashboardPage", () => {
  it("loading дашборда → «Загрузка…»", () => {
    mDash.mockReturnValue(new Promise(() => undefined));
    mSeries.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("ошибка дашборда показывается без карточек", async () => {
    mDash.mockRejectedValue(new Error("dash boom"));
    renderPage();

    expect(await screen.findByText("dash boom")).toBeInTheDocument();
    expect(screen.queryByText("Заказы")).not.toBeInTheDocument();
  });

  it("карточки: значения, дельты и подсказки", async () => {
    renderPage();

    expect(await screen.findByText("Заказы")).toBeInTheDocument();
    expect(screen.getAllByText("Выручка").length).toBeGreaterThan(0);
    expect(screen.getByText("Новые пользователи")).toBeInTheDocument();
    expect(screen.getByText("Возвраты")).toBeInTheDocument();

    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText(/9\s*500,00\s*₽/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getAllByText(/500,00\s*₽/).length).toBeGreaterThan(0);

    expect(screen.getByText("↑ 25.0%")).toBeInTheDocument();
    expect(screen.getByText("↑ 10.5%")).toBeInTheDocument();
    expect(screen.getByText("↓ 5.0%")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();

    expect(
      screen.getByText(/gross: 10\s*000,00\s*₽ · возвраты: 500,00\s*₽/)
    ).toBeInTheDocument();
    expect(screen.getByText("было 8 за пред. 7 дн.")).toBeInTheDocument();
  });

  it("нулевая дельта → «→ 0%»", async () => {
    mDash.mockResolvedValue({ ...DASH, orders_count_delta_pct: 0 });
    renderPage();

    expect(await screen.findByText("→ 0%")).toBeInTheDocument();
  });

  it("топ-товары: таблица и ссылка на заказы", async () => {
    renderPage();

    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/5\s*000,00\s*₽/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Все заказы →" })
    ).toHaveAttribute("href", "/admin/orders");
  });

  it("без топ-товаров → «За период продаж не было.»", async () => {
    mDash.mockResolvedValue({ ...DASH, top_products: [] });
    renderPage();

    expect(
      await screen.findByText("За период продаж не было.")
    ).toBeInTheDocument();
  });

  it("loading серии → «Загрузка графика…»", async () => {
    mSeries.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(await screen.findByText("Загрузка графика…")).toBeInTheDocument();
  });

  it("ошибка серии показывается", async () => {
    mSeries.mockRejectedValue(new Error("series boom"));
    renderPage();

    expect(await screen.findByText("series boom")).toBeInTheDocument();
  });

  it("график: svg с точками и tooltip", async () => {
    renderPage();

    const chart = await screen.findByRole("img", {
      name: "График выручки по дням",
    });
    expect(chart).toBeInTheDocument();
    expect(chart.querySelectorAll("circle")).toHaveLength(2);
    expect(
      screen.getByText(/2026-01-01: 1000\.00 ₽, 2 заказ/)
    ).toBeInTheDocument();
    expect(screen.getAllByText(/01-01/).length).toBeGreaterThan(0);
  });

  it("пустая серия → «Нет данных»", async () => {
    mSeries.mockResolvedValue({ period_days: 7, items: [] });
    renderPage();

    expect(await screen.findByText("Нет данных")).toBeInTheDocument();
  });

  it("смена периода перезапрашивает дашборд и серию", async () => {
    renderPage();
    await screen.findByText("Заказы");

    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "30" },
    });

    await waitFor(() =>
      expect(mDash).toHaveBeenLastCalledWith(30)
    );
    expect(mSeries).toHaveBeenLastCalledWith(30);
  });

  it("скачивание CSV вызывает downloadDashboardCsv с периодом", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Заказы");

    await user.click(screen.getByRole("button", { name: "Скачать CSV" }));

    await waitFor(() => expect(mCsv).toHaveBeenCalledWith(7));
  });

  it("ошибка CSV (Error) → error-toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCsv.mockRejectedValue(new Error("csv boom"));
    renderPage(showToast);
    await screen.findByText("Заказы");

    await user.click(screen.getByRole("button", { name: "Скачать CSV" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("csv boom", "error")
    );
  });

  it("ошибка CSV (не Error) → «Ошибка скачивания»", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCsv.mockRejectedValue("plain");
    renderPage(showToast);
    await screen.findByText("Заказы");

    await user.click(screen.getByRole("button", { name: "Скачать CSV" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("Ошибка скачивания", "error")
    );
  });
});

describe("RevenueChart", () => {
  it("10 точек: прореживание X-подписей и shortMoney K/M", () => {
    const items: DailySeriesItem[] = Array.from({ length: 10 }, (_, i) => ({
      date: `2026-01-${String(i + 1).padStart(2, "0")}`,
      orders_count: i,
      revenue_gross: i === 9 ? "1000000.00" : i === 8 ? "1500.00" : "0",
    }));

    render(<RevenueChart items={items} />);

    expect(
      screen.getByRole("img", { name: "График выручки по дням" })
    ).toBeInTheDocument();
    expect(screen.getByText("1.0M")).toBeInTheDocument();
    expect(screen.getByText("750.0K")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getAllByText(/^01-/)).toHaveLength(5);
    expect(
      screen.getByText(/2026-01-09: 1500\.00 ₽, 8 заказ/)
    ).toBeInTheDocument();
  });

  it("одна точка не делит на ноль", () => {
    render(
      <RevenueChart
        items={[
          { date: "2026-02-01", orders_count: 1, revenue_gross: "100.00" },
        ]}
      />
    );

    expect(
      screen.getByRole("img", { name: "График выручки по дням" })
    ).toBeInTheDocument();
    expect(screen.getByText("02-01")).toBeInTheDocument();
  });
});
