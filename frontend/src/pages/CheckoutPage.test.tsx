import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation, useParams } from "react-router-dom";

import { CheckoutPage } from "./CheckoutPage";
import { renderWithProviders } from "../test/render";
import type { CartContextValue } from "../context/cartContext";
import type { AddressResponse } from "../types/address";
import type { CartItemResponse, CartResponse } from "../types/cart";
import type { OrderResponse } from "../types/order";
import type { PromoCodePreviewResponse } from "../types/promo";

vi.mock("../api/addresses", () => ({
  fetchAddresses: vi.fn(),
  createAddress: vi.fn(),
}));
vi.mock("../api/orders", () => ({
  createOrder: vi.fn(),
}));

import { createAddress, fetchAddresses } from "../api/addresses";
import { createOrder } from "../api/orders";

const mFetchAddresses = vi.mocked(fetchAddresses);
const mCreateAddress = vi.mocked(createAddress);
const mCreateOrder = vi.mocked(createOrder);

function makeItem(overrides: Partial<CartItemResponse> = {}): CartItemResponse {
  return {
    product_id: 1,
    name: "Laptop",
    cover_url: null,
    quantity: 2,
    snapshot_cost: "1000.00",
    current_cost: "1000.00",
    status: "available",
    is_available: true,
    ...overrides,
  };
}

function makeCart(overrides: Partial<CartResponse> = {}): CartResponse {
  const items = overrides.items ?? [makeItem()];
  return {
    items,
    total_items: items.reduce((sum, item) => sum + item.quantity, 0),
    total_cost: "2000.00",
    hidden_items_count: 0,
    ...overrides,
  };
}

function makeAddress(
  id: number,
  overrides: Partial<AddressResponse> = {}
): AddressResponse {
  return {
    id,
    address_line1: `Улица ${id}`,
    address_line2: null,
    city: "Moscow",
    postal_code: "101000",
    country: "Russia",
    is_default: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const PROMO: PromoCodePreviewResponse = {
  code: "SALE10",
  discount_type: "percentage",
  discount_value: "10.00",
  subtotal: "2000.00",
  discount_amount: "200.00",
  final_total: "1800.00",
};

function OrderProbe() {
  const { publicId } = useParams();
  const location = useLocation();
  const state = location.state as { justCreated?: boolean } | null;
  return (
    <div data-testid="order-probe">
      {publicId}:{state?.justCreated === true ? "created" : "plain"}
    </div>
  );
}

function renderCheckout(
  cartOverrides: Partial<CartContextValue> = {},
  showToast = vi.fn()
) {
  return renderWithProviders(
    <Routes>
      <Route path="/checkout" element={<CheckoutPage />} />
      <Route path="/orders/:publicId" element={<OrderProbe />} />
    </Routes>,
    {
      route: "/checkout",
      cart: {
        cart: makeCart(),
        totalItems: 2,
        ...cartOverrides,
      },
      toast: { showToast },
    }
  );
}

beforeEach(() => {
  mFetchAddresses
    .mockReset()
    .mockResolvedValue([
      makeAddress(1, { is_default: true }),
      makeAddress(2, { city: "Kazan" }),
    ]);
  mCreateAddress.mockReset();
  mCreateOrder
    .mockReset()
    .mockResolvedValue({ public_id: "ord-1" } as OrderResponse);
});

describe("CheckoutPage", () => {
  it("loading без cart → LoadingState", () => {
    mFetchAddresses.mockReturnValue(new Promise(() => undefined));
    renderCheckout({ cart: null, loading: true });
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("cart === null без loading → LoadingState", () => {
    mFetchAddresses.mockReturnValue(new Promise(() => undefined));
    renderCheckout({ cart: null, loading: false });
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("error без cart → ErrorState, retry вызывает refreshCart", async () => {
    const user = userEvent.setup();
    const refreshCart = vi.fn().mockRejectedValue(new Error("ignored"));
    renderCheckout({ cart: null, error: "boom", refreshCart });

    expect(screen.getByText(/Ошибка: boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    await waitFor(() => expect(refreshCart).toHaveBeenCalledTimes(1));
  });

  it("пустая корзина → EmptyState и ссылка в каталог", () => {
    mFetchAddresses.mockReturnValue(new Promise(() => undefined));
    renderCheckout({ cart: makeCart({ items: [], total_items: 0 }) });

    expect(screen.getByText("Корзина пуста")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Перейти в каталог" })
    ).toBeInTheDocument();
  });

  it("показывает адреса по умолчанию, состав заказа и заглушку обложки", async () => {
    renderCheckout();

    expect(await screen.findByText(/Moscow/)).toBeInTheDocument();
    const [first] = screen.getAllByRole("radio");
    await waitFor(() => expect(first).toBeChecked());
    expect(screen.getByText("По умолчанию")).toBeInTheDocument();
    expect(screen.getByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText("Нет изображения")).toBeInTheDocument();
    expect(screen.getAllByText(/2\s*000,00\s*₽/).length).toBeGreaterThan(0);
  });

  it("выбор другого адреса обновляет radio", async () => {
    const user = userEvent.setup();
    renderCheckout();

    await screen.findAllByRole("radio");
    const second = screen.getAllByRole("radio")[1];
    await user.click(second);

    expect(second).toBeChecked();
    expect(screen.getAllByRole("radio")[0]).not.toBeChecked();
  });

  it("нет адресов → подсказка, форма без «Отмена», создание и выбор адреса", async () => {
    const user = userEvent.setup();
    mFetchAddresses.mockResolvedValue([]);
    mCreateAddress.mockResolvedValue(makeAddress(3, { city: "Sochi" }));
    const showToast = vi.fn();
    renderCheckout({}, showToast);

    expect(
      await screen.findByText("У вас пока нет адресов доставки.")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Добавить адрес" }));
    expect(
      screen.queryByRole("button", { name: "Отмена" })
    ).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Адрес (строка 1) *"), "  Морская 5 ");
    await user.type(screen.getByLabelText("Город *"), "Sochi");
    await user.type(screen.getByLabelText("Почтовый индекс *"), "354000");
    await user.type(screen.getByLabelText("Страна *"), "Russia");
    await user.click(screen.getByRole("button", { name: "Сохранить адрес" }));

    await waitFor(() =>
      expect(mCreateAddress).toHaveBeenCalledWith({
        address_line1: "Морская 5",
        address_line2: null,
        city: "Sochi",
        postal_code: "354000",
        country: "Russia",
        is_default: false,
      })
    );
    expect(showToast).toHaveBeenCalledWith("Адрес сохранён", "success");
    expect(screen.queryByLabelText("Адрес (строка 1) *")).not.toBeInTheDocument();
    expect(await screen.findByText(/Sochi/)).toBeInTheDocument();
    expect(screen.getByRole("radio")).toBeChecked();
  });

  it("ошибка загрузки адресов → retry перезапрашивает список", async () => {
    const user = userEvent.setup();
    mFetchAddresses
      .mockRejectedValueOnce(new Error("addr boom"))
      .mockResolvedValueOnce([makeAddress(1, { is_default: true })]);
    renderCheckout();

    expect(await screen.findByText(/Ошибка: addr boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText(/Moscow/)).toBeInTheDocument();
    expect(mFetchAddresses).toHaveBeenCalledTimes(2);
  });

  it("адреса загружаются → LoadingState в секции адреса", () => {
    mFetchAddresses.mockReturnValue(new Promise(() => undefined));
    renderCheckout();

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("добавление адреса из списка и отмена формы", async () => {
    const user = userEvent.setup();
    renderCheckout();

    await screen.findAllByRole("radio");
    await user.click(
      screen.getByRole("button", { name: "Добавить новый адрес" })
    );
    expect(screen.getByLabelText("Адрес (строка 1) *")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(
      screen.queryByLabelText("Адрес (строка 1) *")
    ).not.toBeInTheDocument();
  });

  it("пустой промокод → ошибка «Введите промокод»", async () => {
    const user = userEvent.setup();
    renderCheckout();

    await screen.findAllByRole("radio");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(screen.getByText("Введите промокод")).toBeInTheDocument();
  });

  it("успешный промокод показывает скидку и итог", async () => {
    const user = userEvent.setup();
    let resolvePromo: (value: PromoCodePreviewResponse) => void = () => undefined;
    const applyPromo = vi.fn(
      () =>
        new Promise<PromoCodePreviewResponse>((resolve) => {
          resolvePromo = resolve;
        })
    );
    renderCheckout({ cart: makeCart(), applyPromo });

    await screen.findAllByRole("radio");
    await user.type(screen.getByLabelText("Промокод"), "SALE10");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(
      screen.getByRole("button", { name: "Проверяем..." })
    ).toBeDisabled();
    expect(applyPromo).toHaveBeenCalledWith("SALE10");

    resolvePromo(PROMO);

    expect(await screen.findByText("Скидка")).toBeInTheDocument();
    expect(screen.getByText(/200,00\s*₽/)).toBeInTheDocument();
    expect(screen.getByText(/1\s*800,00\s*₽/)).toBeInTheDocument();
  });

  it("ошибка промокода показывается и результат не рендерится", async () => {
    const user = userEvent.setup();
    const applyPromo = vi.fn().mockRejectedValue(new Error("promo boom"));
    renderCheckout({ cart: makeCart(), applyPromo });

    await screen.findAllByRole("radio");
    await user.type(screen.getByLabelText("Промокод"), "BAD");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(await screen.findByText("promo boom")).toBeInTheDocument();
    expect(screen.queryByText("Скидка")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Применить" })
    ).toBeEnabled();
  });

  it("недоступный товар → предупреждение и кнопка оформления заблокирована", async () => {
    renderCheckout({
      cart: makeCart({
        items: [makeItem({ is_available: false, status: "out_of_stock" })],
      }),
    });

    expect(await screen.findByText(/недоступные товары/)).toBeInTheDocument();
    await screen.findAllByRole("radio");
    expect(
      screen.getByRole("button", { name: "Оформить заказ" })
    ).toBeDisabled();
  });

  it("успешное оформление: createOrder, refreshCart, toast и переход", async () => {
    const user = userEvent.setup();
    const refreshCart = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    renderCheckout({ cart: makeCart(), refreshCart }, showToast);

    await screen.findAllByRole("radio");
    await user.type(screen.getByLabelText("Промокод"), " SALE10 ");
    await user.click(screen.getByRole("button", { name: "Оформить заказ" }));

    await waitFor(() =>
      expect(mCreateOrder).toHaveBeenCalledWith(
        { address_id: 1, promo_code: "SALE10" },
        expect.any(String)
      )
    );
    expect(refreshCart).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(
      "Заказ создан. Осталось оплатить.",
      "success"
    );
    expect(await screen.findByTestId("order-probe")).toHaveTextContent(
      "ord-1:created"
    );
  });

  it("ошибка оформления показывается, кнопка снова активна", async () => {
    const user = userEvent.setup();
    mCreateOrder.mockRejectedValue(new Error("order boom"));
    renderCheckout();

    await screen.findAllByRole("radio");
    await user.click(screen.getByRole("button", { name: "Оформить заказ" }));

    expect(await screen.findByText("order boom")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Оформить заказ" })
    ).toBeEnabled();
  });

  it("во время отправки кнопка показывает «Оформляем...» и disabled", async () => {
    const user = userEvent.setup();
    let resolveOrder: (value: OrderResponse) => void = () => undefined;
    mCreateOrder.mockReturnValue(
      new Promise<OrderResponse>((resolve) => {
        resolveOrder = resolve;
      })
    );
    renderCheckout();

    await screen.findAllByRole("radio");
    await user.click(screen.getByRole("button", { name: "Оформить заказ" }));

    const pending = screen.getByRole("button", { name: "Оформляем..." });
    expect(pending).toBeDisabled();

    resolveOrder({ public_id: "ord-2" } as OrderResponse);
    await waitFor(() =>
      expect(screen.getByTestId("order-probe")).toHaveTextContent("ord-2:created")
    );
  });

  it("адрес со второй строкой и товар с обложкой", async () => {
    mFetchAddresses.mockResolvedValue([
      makeAddress(1, { address_line2: "кв. 5", is_default: true }),
    ]);
    renderCheckout({
      cart: makeCart({
        items: [makeItem({ cover_url: "https://cdn.example/laptop.png" })],
      }),
    });

    expect(await screen.findByText(/кв\. 5/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Laptop" })).toHaveAttribute(
      "src",
      "https://cdn.example/laptop.png"
    );
  });

  it("форма адреса: валидация обязательных полей и ошибка сохранения", async () => {
    const user = userEvent.setup();
    mFetchAddresses.mockResolvedValue([]);
    renderCheckout();

    await screen.findByText("У вас пока нет адресов доставки.");
    await user.click(screen.getByRole("button", { name: "Добавить адрес" }));

    const form = screen
      .getByRole("button", { name: "Сохранить адрес" })
      .closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    expect(
      await screen.findByText("Заполните обязательные поля адреса")
    ).toBeInTheDocument();
    expect(mCreateAddress).not.toHaveBeenCalled();

    mCreateAddress.mockRejectedValue(new Error("addr fail"));
    await user.type(screen.getByLabelText("Адрес (строка 1) *"), "Ленина 1");
    await user.type(screen.getByLabelText("Город *"), "Moscow");
    await user.type(screen.getByLabelText("Почтовый индекс *"), "101000");
    await user.type(screen.getByLabelText("Страна *"), "Russia");
    await user.click(screen.getByRole("button", { name: "Сохранить адрес" }));

    expect(await screen.findByText("addr fail")).toBeInTheDocument();
    expect(screen.getByLabelText("Адрес (строка 1) *")).toBeInTheDocument();
  });
});
