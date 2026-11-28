import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AddressesPage } from "./AddressesPage";
import { renderWithProviders } from "../test/render";
import type { AddressResponse } from "../types/address";

vi.mock("../api/addresses", () => ({
  fetchAddresses: vi.fn(),
  createAddress: vi.fn(),
  updateAddress: vi.fn(),
  deleteAddress: vi.fn(),
  setDefaultAddress: vi.fn(),
}));

import {
  createAddress,
  deleteAddress,
  fetchAddresses,
  setDefaultAddress,
} from "../api/addresses";

const mFetch = vi.mocked(fetchAddresses);
const mCreate = vi.mocked(createAddress);
const mDelete = vi.mocked(deleteAddress);
const mSetDefault = vi.mocked(setDefaultAddress);

function makeAddress(
  id: number,
  overrides: Partial<AddressResponse> = {}
): AddressResponse {
  return {
    id,
    address_line1: `Улица ${id}`,
    address_line2: null,
    city: id === 1 ? "Moscow" : "Kazan",
    postal_code: "101000",
    country: "Russia",
    is_default: id === 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage(showToast = vi.fn()) {
  return renderWithProviders(<AddressesPage />, {
    toast: { showToast },
  });
}

function cardByCity(city: string) {
  const card = screen.getByText(new RegExp(city)).closest(".address-card");
  if (card === null) throw new Error("card not found");
  return card as HTMLElement;
}

function fillForm(city: string) {
  fireEvent.change(screen.getByLabelText("Адрес (строка 1) *"), {
    target: { value: "Ленина 1" },
  });
  fireEvent.change(screen.getByLabelText("Город *"), {
    target: { value: city },
  });
  fireEvent.change(screen.getByLabelText("Почтовый индекс *"), {
    target: { value: "101000" },
  });
  fireEvent.change(screen.getByLabelText("Страна *"), {
    target: { value: "Russia" },
  });
}

beforeEach(() => {
  mFetch.mockReset().mockResolvedValue([makeAddress(1), makeAddress(2)]);
  mCreate.mockReset();
  mDelete.mockReset();
  mSetDefault.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AddressesPage", () => {
  it("loading без адресов → LoadingState", () => {
    mFetch.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("ошибка → ErrorState, retry перезапрашивает", async () => {
    const user = userEvent.setup();
    mFetch
      .mockRejectedValueOnce(new Error("addr boom"))
      .mockResolvedValueOnce([makeAddress(1)]);
    renderPage();

    expect(await screen.findByText(/Ошибка: addr boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText(/Moscow/)).toBeInTheDocument();
    expect(mFetch).toHaveBeenCalledTimes(2);
  });

  it("пустой список → EmptyState и кнопка добавления", async () => {
    mFetch.mockResolvedValue([]);
    renderPage();

    expect(
      await screen.findByText("Сохранённых адресов пока нет")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Добавить адрес" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "← В каталог" })
    ).toHaveAttribute("href", "/");
  });

  it("список: адреса, вторая строка, бейдж и действия", async () => {
    mFetch.mockResolvedValue([
      makeAddress(1, { address_line2: "кв. 5" }),
      makeAddress(2),
    ]);
    renderPage();

    expect(await screen.findByText(/Moscow/)).toBeInTheDocument();
    expect(screen.getByText(/кв\. 5/)).toBeInTheDocument();
    expect(screen.getByText(/Kazan/)).toBeInTheDocument();
    expect(screen.getAllByText(/101000, Russia/)).toHaveLength(2);
    expect(screen.getByText("По умолчанию")).toBeInTheDocument();

    const first = cardByCity("Moscow");
    expect(
      within(first).queryByRole("button", { name: "Сделать основным" })
    ).not.toBeInTheDocument();
    expect(
      within(first).getByRole("button", { name: "Удалить" })
    ).toBeInTheDocument();

    const second = cardByCity("Kazan");
    expect(
      within(second).getByRole("button", { name: "Сделать основным" })
    ).toBeInTheDocument();
  });

  it("форма добавления открывается и закрывается", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Moscow/);

    await user.click(screen.getByRole("button", { name: "Добавить адрес" }));
    expect(
      screen.getByRole("heading", { name: "Новый адрес" })
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(
      screen.queryByRole("heading", { name: "Новый адрес" })
    ).not.toBeInTheDocument();
  });

  it("создание обычного адреса добавляет его в список", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCreate.mockResolvedValue(makeAddress(3, { city: "Sochi", is_default: false }));
    renderPage(showToast);
    await screen.findByText(/Moscow/);

    await user.click(screen.getByRole("button", { name: "Добавить адрес" }));
    fillForm("Sochi");
    await user.click(screen.getByRole("button", { name: "Сохранить адрес" }));

    await waitFor(() => expect(mCreate).toHaveBeenCalledTimes(1));
    expect(showToast).toHaveBeenCalledWith("Адрес сохранён", "success");
    expect(await screen.findByText(/Sochi/)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Новый адрес" })
    ).not.toBeInTheDocument();
  });

  it("создание дефолтного адреса снимает бейдж с прежнего", async () => {
    const user = userEvent.setup();
    mCreate.mockResolvedValue(makeAddress(3, { city: "Sochi", is_default: true }));
    renderPage();
    await screen.findByText(/Moscow/);
    expect(screen.getAllByText("По умолчанию")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Добавить адрес" }));
    fillForm("Sochi");
    await user.click(screen.getByLabelText("Сделать адресом по умолчанию"));
    await user.click(screen.getByRole("button", { name: "Сохранить адрес" }));

    expect(await screen.findByText(/Sochi/)).toBeInTheDocument();
    expect(screen.getAllByText("По умолчанию")).toHaveLength(1);
    expect(
      within(cardByCity("Sochi")).getByText("По умолчанию")
    ).toBeInTheDocument();
  });

  it("удаление с подтверждением убирает адрес и показывает info-toast", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const showToast = vi.fn();
    mDelete.mockResolvedValue(undefined);
    renderPage(showToast);
    await screen.findByText(/Moscow/);

    await user.click(
      within(cardByCity("Moscow")).getByRole("button", { name: "Удалить" })
    );

    await waitFor(() => expect(mDelete).toHaveBeenCalledWith(1));
    expect(showToast).toHaveBeenCalledWith("Адрес удалён", "info");
    expect(screen.queryByText(/Moscow/)).not.toBeInTheDocument();
    expect(screen.getByText(/Kazan/)).toBeInTheDocument();
  });

  it("удаление отменено → API не вызван", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    renderPage();
    await screen.findByText(/Moscow/);

    await user.click(
      within(cardByCity("Moscow")).getByRole("button", { name: "Удалить" })
    );

    expect(mDelete).not.toHaveBeenCalled();
    expect(screen.getByText(/Moscow/)).toBeInTheDocument();
  });

  it("ошибка удаления → error-toast, адрес остаётся", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const showToast = vi.fn();
    mDelete.mockRejectedValue(new Error("delete addr boom"));
    renderPage(showToast);
    await screen.findByText(/Moscow/);

    await user.click(
      within(cardByCity("Moscow")).getByRole("button", { name: "Удалить" })
    );

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("delete addr boom", "error")
    );
    expect(screen.getByText(/Moscow/)).toBeInTheDocument();
  });

  it("во время удаления кнопки этой карточки disabled", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    let resolveDelete: (value: void) => void = () => undefined;
    mDelete.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveDelete = resolve;
      })
    );
    renderPage();
    await screen.findByText(/Moscow/);

    const first = cardByCity("Moscow");
    await user.click(within(first).getByRole("button", { name: "Удалить" }));

    expect(within(first).getByRole("button", { name: "Удалить" })).toBeDisabled();
    expect(
      within(cardByCity("Kazan")).getByRole("button", { name: "Удалить" })
    ).toBeEnabled();

    resolveDelete();
    await waitFor(() => expect(mDelete).toHaveBeenCalledTimes(1));
  });

  it("сделать основным: API, перестановка бейджа и toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mSetDefault.mockResolvedValue(
      makeAddress(2, { is_default: true })
    );
    renderPage(showToast);
    await screen.findByText(/Moscow/);

    await user.click(
      within(cardByCity("Kazan")).getByRole("button", {
        name: "Сделать основным",
      })
    );

    await waitFor(() => expect(mSetDefault).toHaveBeenCalledWith(2));
    expect(showToast).toHaveBeenCalledWith(
      "Адрес по умолчанию обновлён",
      "success"
    );
    expect(
      within(cardByCity("Kazan")).getByText("По умолчанию")
    ).toBeInTheDocument();
    expect(screen.getAllByText("По умолчанию")).toHaveLength(1);
    expect(
      within(cardByCity("Moscow")).queryByText("По умолчанию")
    ).not.toBeInTheDocument();
  });

  it("ошибка смены дефолта → error-toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mSetDefault.mockRejectedValue(new Error("default boom"));
    renderPage(showToast);
    await screen.findByText(/Moscow/);

    await user.click(
      within(cardByCity("Kazan")).getByRole("button", {
        name: "Сделать основным",
      })
    );

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("default boom", "error")
    );
  });

  it("во время смены дефолта кнопки карточки disabled", async () => {
    const user = userEvent.setup();
    let resolveDefault: (value: AddressResponse) => void = () => undefined;
    mSetDefault.mockReturnValue(
      new Promise<AddressResponse>((resolve) => {
        resolveDefault = resolve;
      })
    );
    renderPage();
    await screen.findByText(/Moscow/);

    const second = cardByCity("Kazan");
    await user.click(
      within(second).getByRole("button", { name: "Сделать основным" })
    );

    expect(
      within(second).getByRole("button", { name: "Сделать основным" })
    ).toBeDisabled();
    expect(within(second).getByRole("button", { name: "Удалить" })).toBeDisabled();

    resolveDefault(makeAddress(2, { is_default: true }));
    await waitFor(() => expect(mSetDefault).toHaveBeenCalledTimes(1));
  });
});
