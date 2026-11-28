import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { OrderDetailPage } from "./OrderDetailPage";
import { renderWithProviders } from "../test/render";
import type { OrderItemResponse, OrderResponse } from "../types/order";
import type { PaymentResponse } from "../types/payment";

vi.mock("../api/orders", () => ({
  fetchOrder: vi.fn(),
  payOrder: vi.fn(),
}));

import { fetchOrder, payOrder } from "../api/orders";

const mFetchOrder = vi.mocked(fetchOrder);
const mPayOrder = vi.mocked(payOrder);

function makeItem(overrides: Partial<OrderItemResponse> = {}): OrderItemResponse {
  return {
    public_id: "oi-1",
    product: {
      id: 1,
      name: "Laptop",
      cover_url: null,
      status: "available",
    },
    product_cost: "1000.00",
    product_count: 2,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makePayment(
  overrides: Partial<PaymentResponse> = {}
): PaymentResponse {
  return {
    public_id: "pay-1",
    status: "completed",
    amount: "1800.00",
    currency: "RUB",
    method: "card",
    external_id: null,
    paid_at: "2026-01-02T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeOrder(overrides: Partial<OrderResponse> = {}): OrderResponse {
  return {
    public_id: "ord-1",
    status: "pending",
    subtotal: "2000.00",
    discount_amount: "200.00",
    total: "1800.00",
    promo_code: "SALE10",
    shipping_address: {
      id: 1,
      city: "Moscow",
      address_line1: "Ленина 1",
      postal_code: "101000",
      country: "Russia",
    },
    items: [makeItem()],
    payments: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderOrder(route = "/orders/ord-1", routeState?: unknown) {
  return renderWithProviders(
    <Routes>
      <Route path="/orders/:publicId" element={<OrderDetailPage />} />
    </Routes>,
    { route, routeState }
  );
}

beforeEach(() => {
  mFetchOrder.mockReset().mockResolvedValue(makeOrder());
  mPayOrder.mockReset();
});

describe("OrderDetailPage", () => {
  it("загрузка заказа → LoadingState", () => {
    mFetchOrder.mockReturnValue(new Promise(() => undefined));
    renderOrder();

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("ошибка загрузки → ErrorState, retry перезапрашивает заказ", async () => {
    const user = userEvent.setup();
    mFetchOrder
      .mockRejectedValueOnce(new Error("order boom"))
      .mockResolvedValueOnce(makeOrder());
    renderOrder();

    expect(await screen.findByText(/Ошибка: order boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("heading", { name: "Заказ ord-1" })
    ).toBeInTheDocument();
    expect(mFetchOrder).toHaveBeenCalledTimes(2);
  });

  it("fetch вернул null → LoadingState", async () => {
    mFetchOrder.mockResolvedValue(null as unknown as OrderResponse);
    renderOrder();

    await waitFor(() => expect(mFetchOrder).toHaveBeenCalled());
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("без publicId → ошибка идентификатора, fetchOrder не вызывается", () => {
    renderWithProviders(<OrderDetailPage />, { route: "/" });

    expect(
      screen.getByText("Ошибка: Некорректный идентификатор заказа")
    ).toBeInTheDocument();
    expect(mFetchOrder).not.toHaveBeenCalled();
  });

  it("pending-заказ: состав, адрес, суммы, промокод и форма оплаты", async () => {
    renderOrder();

    expect(
      await screen.findByRole("heading", { name: "Заказ ord-1" })
    ).toBeInTheDocument();
    expect(screen.getByText("Ожидает оплаты")).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Laptop" })).toHaveAttribute(
      "href",
      "/products/1"
    );
    expect(screen.getByText("2 шт.")).toBeInTheDocument();
    expect(screen.getByText(/Ленина 1/)).toBeInTheDocument();
    expect(screen.getByText("Платежей пока нет.")).toBeInTheDocument();

    expect(screen.getByText("Сумма")).toBeInTheDocument();
    expect(screen.getByText("Скидка")).toBeInTheDocument();
    expect(screen.getByText("Промокод")).toBeInTheDocument();
    expect(screen.getByText("SALE10")).toBeInTheDocument();
    expect(screen.getByText(/1\s*800,00\s*₽/)).toBeInTheDocument();

    expect(screen.getByLabelText("Способ оплаты")).toHaveValue("card");
    expect(
      screen.getByRole("button", { name: "Оплатить" })
    ).toBeInTheDocument();
  });

  it("justCreated из location.state показывает подсказку", async () => {
    renderOrder("/orders/ord-1", { justCreated: true });

    expect(
      await screen.findByText(/Заказ создан\. Выберите способ оплаты/)
    ).toBeInTheDocument();
  });

  it("без скидки и промокода соответствующие строки скрыты", async () => {
    mFetchOrder.mockResolvedValue(
      makeOrder({ discount_amount: null, promo_code: null })
    );
    renderOrder();

    await screen.findByRole("heading", { name: "Заказ ord-1" });
    expect(screen.queryByText("Скидка")).not.toBeInTheDocument();
    expect(screen.queryByText("Промокод")).not.toBeInTheDocument();
  });

  it("обложки: img для товара с cover_url и заглушка без неё", async () => {
    mFetchOrder.mockResolvedValue(
      makeOrder({
        items: [
          makeItem({
            public_id: "oi-1",
            product: {
              id: 1,
              name: "Laptop",
              cover_url: "https://cdn.example/laptop.png",
              status: "available",
            },
          }),
          makeItem({
            public_id: "oi-2",
            product: {
              id: 2,
              name: "Mouse",
              cover_url: null,
              status: "available",
            },
          }),
        ],
      })
    );
    renderOrder();

    expect(
      await screen.findByRole("img", { name: "Laptop" })
    ).toHaveAttribute("src", "https://cdn.example/laptop.png");
    expect(screen.getByText("Нет изображения")).toBeInTheDocument();
  });

  it("список платежей: метод, сумма, статус, paid_at/created_at", async () => {
    mFetchOrder.mockResolvedValue(
      makeOrder({
        payments: [
          makePayment({
            public_id: "pay-1",
            method: "card",
            status: "completed",
            amount: "1000.00",
            paid_at: "2026-01-02T00:00:00Z",
          }),
          makePayment({
            public_id: "pay-2",
            method: "crypto",
            status: "failed",
            amount: "700.00",
            paid_at: null,
            created_at: "2026-01-03T00:00:00Z",
          }),
        ],
      })
    );
    renderOrder();

    expect(await screen.findAllByText("Банковская карта")).not.toHaveLength(0);
    expect(screen.getAllByText("Криптовалюта").length).toBeGreaterThan(0);
    expect(screen.getByText("Завершён")).toBeInTheDocument();
    expect(screen.getByText("Ошибка")).toBeInTheDocument();
    expect(screen.getAllByText(/1\s*000,00\s*₽/).length).toBeGreaterThan(0);
    expect(screen.getByText(/700,00\s*₽/)).toBeInTheDocument();
  });

  it("оплаченный заказ не показывает форму оплаты", async () => {
    mFetchOrder.mockResolvedValue(makeOrder({ status: "paid" }));
    renderOrder();

    expect(await screen.findByText("Оплачен")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Оплатить" })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Оплата")).not.toBeInTheDocument();
  });

  it("успешная оплата: payOrder, обновление заказа и toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const paid = makeOrder({
      status: "paid",
      payments: [makePayment()],
    });
    mFetchOrder
      .mockResolvedValueOnce(makeOrder())
      .mockResolvedValueOnce(paid);
    mPayOrder.mockResolvedValue({
      public_id: "pay-1",
      status: "completed",
      amount: "1800.00",
      currency: "RUB",
      method: "bank_transfer",
      external_id: null,
      paid_at: "2026-01-02T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    });

    renderWithProviders(
      <Routes>
        <Route path="/orders/:publicId" element={<OrderDetailPage />} />
      </Routes>,
      { route: "/orders/ord-1", toast: { showToast } }
    );

    await screen.findByRole("heading", { name: "Заказ ord-1" });
    await user.selectOptions(
      screen.getByLabelText("Способ оплаты"),
      "bank_transfer"
    );
    await user.click(screen.getByRole("button", { name: "Оплатить" }));

    await waitFor(() =>
      expect(mPayOrder).toHaveBeenCalledWith("ord-1", {
        method: "bank_transfer",
        external_id: expect.any(String),
      })
    );
    expect(mFetchOrder).toHaveBeenCalledTimes(2);
    expect(showToast).toHaveBeenCalledWith("Заказ оплачен", "success");
    expect(await screen.findByText("Оплачен")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Оплатить" })
    ).not.toBeInTheDocument();
  });

  it("во время оплаты кнопка показывает «Оплачиваем...» и disabled", async () => {
    const user = userEvent.setup();
    let resolvePay: (value: PaymentResponse) => void = () => undefined;
    mPayOrder.mockReturnValue(
      new Promise<PaymentResponse>((resolve) => {
        resolvePay = resolve;
      })
    );
    renderOrder();

    await screen.findByRole("heading", { name: "Заказ ord-1" });
    await user.click(screen.getByRole("button", { name: "Оплатить" }));

    expect(
      screen.getByRole("button", { name: "Оплачиваем..." })
    ).toBeDisabled();

    resolvePay(makePayment());
    await waitFor(() =>
      expect(mFetchOrder).toHaveBeenCalledTimes(2)
    );
  });

  it("ошибка оплаты показывается, кнопка снова активна", async () => {
    const user = userEvent.setup();
    mPayOrder.mockRejectedValue(new Error("pay boom"));
    renderOrder();

    await screen.findByRole("heading", { name: "Заказ ord-1" });
    await user.click(screen.getByRole("button", { name: "Оплатить" }));

    expect(await screen.findByText("pay boom")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Оплатить" })
    ).toBeEnabled();
  });
});
