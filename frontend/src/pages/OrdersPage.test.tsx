import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { OrdersPage } from "./OrdersPage";
import { renderWithProviders } from "../test/render";
import { listOrders } from "../api/orders";
import type { Paginated } from "../types/common";
import type { OrderListItem } from "../types/order";

vi.mock("../api/orders", () => ({ listOrders: vi.fn() }));

const mList = vi.mocked(listOrders);

function makeOrder(overrides: Partial<OrderListItem> = {}): OrderListItem {
  return {
    public_id: "12345678-aaaa-bbbb-cccc-ddddeeeeffff",
    status: "paid",
    discount_amount: "100.00",
    total: "1900.00",
    items_count: 3,
    created_at: "2026-01-02T10:00:00Z",
    ...overrides,
  };
}

function makePage(
  items: OrderListItem[],
  total = items.length,
  page = 1
): Paginated<OrderListItem> {
  return { items, total, page, page_size: 10 };
}

beforeEach(() => {
  mList.mockReset();
});

describe("OrdersPage", () => {
  it("загружает список заказов", async () => {
    mList.mockResolvedValue(makePage([makeOrder()]));
    renderWithProviders(<OrdersPage />);

    expect(await screen.findByText("Заказ 12345678")).toBeInTheDocument();
    expect(screen.getAllByText("Оплачен").length).toBeGreaterThan(0);
    expect(screen.getByText("3 поз.")).toBeInTheDocument();
    expect(screen.getByText(/1\s*900,00\s*₽/)).toBeInTheDocument();
    expect(screen.getByText(/Скидка: −100,00\s*₽/)).toBeInTheDocument();
  });

  it("пустой список → EmptyState", async () => {
    mList.mockResolvedValue(makePage([]));
    renderWithProviders(<OrdersPage />);

    expect(await screen.findByText("Заказов пока нет")).toBeInTheDocument();
  });

  it("loading → LoadingState", async () => {
    let resolve!: (value: Paginated<OrderListItem>) => void;
    mList.mockReturnValue(
      new Promise<Paginated<OrderListItem>>((r) => {
        resolve = r;
      })
    );
    renderWithProviders(<OrdersPage />);

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();

    await act(async () => {
      resolve(makePage([]));
    });
  });

  it("ошибка → ErrorState, retry перезапрашивает", async () => {
    const user = userEvent.setup();
    mList
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(makePage([makeOrder()]));
    renderWithProviders(<OrdersPage />);

    expect(await screen.findByText(/Ошибка: boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    await waitFor(() => expect(mList).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Заказ 12345678")).toBeInTheDocument();
  });

  it("смена статуса сбрасывает страницу и передаёт status", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([makeOrder()]));
    renderWithProviders(<OrdersPage />);
    await screen.findByText("Заказ 12345678");

    await user.selectOptions(screen.getByRole("combobox"), "paid");

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, status: "paid" })
      )
    );
  });

  it("пагинация: переход на следующую страницу", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([makeOrder()], 25));
    renderWithProviders(<OrdersPage />);

    expect(
      await screen.findByText("Страница 1 из 3 (всего 25)")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Предыдущая страница" })
    ).toBeDisabled();

    await user.click(
      screen.getByRole("button", { name: "Следующая страница" })
    );

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );
  });

  it("без скидки не показывает строку скидки", async () => {
    mList.mockResolvedValue(
      makePage([makeOrder({ discount_amount: null })])
    );
    renderWithProviders(<OrdersPage />);

    await screen.findByText("Заказ 12345678");
    expect(screen.queryByText(/Скидка:/)).not.toBeInTheDocument();
  });
});
