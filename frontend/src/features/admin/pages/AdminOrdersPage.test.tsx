import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdminOrdersPage } from "./AdminOrdersPage";
import { renderWithProviders } from "../../../test/render";
import type { Paginated } from "../../../types/common";
import type { OrderListItem } from "../../../types/order";

vi.mock("../../../api/admin", () => ({
  listAdminOrders: vi.fn(),
  updateAdminOrderStatus: vi.fn(),
}));

import {
  listAdminOrders,
  updateAdminOrderStatus,
} from "../../../api/admin";

const mList = vi.mocked(listAdminOrders);
const mUpdate = vi.mocked(updateAdminOrderStatus);

const ORDER: OrderListItem = {
  public_id: "abcdef1234567890",
  status: "paid",
  discount_amount: "200.00",
  total: "1800.00",
  items_count: 2,
  created_at: "2026-01-01T00:00:00Z",
};

function makePage(
  items: OrderListItem[],
  total = items.length
): Paginated<OrderListItem> {
  return { items, total, page: 1, page_size: 20 };
}

function renderPage(showToast = vi.fn()) {
  return renderWithProviders(<AdminOrdersPage />, {
    toast: { showToast },
  });
}

function getRow() {
  const row = screen.getByText("#abcdef12").closest("tr");
  if (row === null) throw new Error("row not found");
  return row;
}

beforeEach(() => {
  mList.mockReset().mockResolvedValue(makePage([ORDER]));
  mUpdate.mockReset();
});

describe("AdminOrdersPage", () => {
  it("loading → «Загрузка…»", () => {
    mList.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("ошибка загрузки → alert с retry", async () => {
    const user = userEvent.setup();
    mList
      .mockRejectedValueOnce(new Error("orders boom"))
      .mockResolvedValueOnce(makePage([ORDER]));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("orders boom");
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("#abcdef12")).toBeInTheDocument();
    expect(mList).toHaveBeenCalledTimes(2);
  });

  it("пустой список → «Заказов нет.» без пагинации", async () => {
    mList.mockResolvedValue(makePage([], 0));
    renderPage();

    expect(await screen.findByText("Заказов нет.")).toBeInTheDocument();
    expect(screen.queryByText(/Страница/)).not.toBeInTheDocument();
  });

  it("рендерит строку заказа", async () => {
    renderPage();

    expect(await screen.findByText("#abcdef12")).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/1\s*800,00\s*₽/)).toBeInTheDocument();
    expect(screen.getAllByText("Оплачен").length).toBeGreaterThan(0);

    const row = getRow();
    expect(within(row).getByRole("combobox")).toHaveValue("paid");
    expect(screen.queryByText(/Страница/)).not.toBeInTheDocument();
  });

  it("фильтр статуса передаёт status и сбрасывает страницу", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([ORDER], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3 (всего 45)");

    await user.click(
      screen.getByRole("button", { name: "Следующая страница" })
    );
    expect(
      await screen.findByText("Страница 2 из 3 (всего 45)")
    ).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("Все статусы"), {
      target: { value: "canceled" },
    });

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, status: "canceled" })
      )
    );
  });

  it("смена статуса: updateAdminOrderStatus, toast и reload", async () => {
    const showToast = vi.fn();
    mList
      .mockResolvedValueOnce(makePage([ORDER]))
      .mockResolvedValueOnce(makePage([{ ...ORDER, status: "shipped" }]));
    mUpdate.mockResolvedValue({} as never);
    renderPage(showToast);
    await screen.findByText("#abcdef12");

    const row = getRow();
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "shipped" },
    });

    await waitFor(() =>
      expect(mUpdate).toHaveBeenCalledWith("abcdef1234567890", "shipped")
    );
    expect(showToast).toHaveBeenCalledWith(
      "Статус заказа обновлён",
      "success"
    );
    await waitFor(() => expect(mList).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(getRow()).getByRole("combobox")).toHaveValue("shipped")
    );
  });

  it("ошибка смены статуса → error-toast", async () => {
    const showToast = vi.fn();
    mUpdate.mockRejectedValue(new Error("status boom"));
    renderPage(showToast);
    await screen.findByText("#abcdef12");

    const row = getRow();
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "delivered" },
    });

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("status boom", "error")
    );
  });

  it("во время обновления select строки disabled", async () => {
    let resolveUpdate: (value: unknown) => void = () => undefined;
    mUpdate.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      }) as never
    );
    renderPage();
    await screen.findByText("#abcdef12");

    const row = getRow();
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "shipped" },
    });

    expect(within(row).getByRole("combobox")).toBeDisabled();

    resolveUpdate({});
    await waitFor(() => expect(mList).toHaveBeenCalledTimes(2));
  });

  it("пагинация: вперёд/назад и границы", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([ORDER], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3 (всего 45)");

    expect(
      screen.getByRole("button", { name: "Предыдущая страница" })
    ).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Следующая страница" })
    );
    expect(
      await screen.findByText("Страница 2 из 3 (всего 45)")
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Следующая страница" })
    );
    expect(
      await screen.findByText("Страница 3 из 3 (всего 45)")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Следующая страница" })
    ).toBeDisabled();

    await user.click(
      screen.getByRole("button", { name: "Предыдущая страница" })
    );
    expect(
      await screen.findByText("Страница 2 из 3 (всего 45)")
    ).toBeInTheDocument();
  });
});
