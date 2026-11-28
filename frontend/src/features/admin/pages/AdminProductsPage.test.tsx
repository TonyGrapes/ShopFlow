import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdminProductsPage } from "./AdminProductsPage";
import { renderWithProviders } from "../../../test/render";
import type { Paginated } from "../../../types/common";
import type { ProductListItem } from "../../../types/product";

vi.mock("../../../api/admin", () => ({
  listAdminProducts: vi.fn(),
  createAdminProduct: vi.fn(),
  updateAdminProduct: vi.fn(),
  deleteAdminProduct: vi.fn(),
}));

import {
  createAdminProduct,
  deleteAdminProduct,
  listAdminProducts,
  updateAdminProduct,
} from "../../../api/admin";

const mList = vi.mocked(listAdminProducts);
const mCreate = vi.mocked(createAdminProduct);
const mUpdate = vi.mocked(updateAdminProduct);
const mDelete = vi.mocked(deleteAdminProduct);

const PRODUCT: ProductListItem = {
  id: 1,
  name: "Laptop",
  cost: "1999.99",
  status: "available",
  cover_url: null,
  category: null,
};

function makePage(
  items: ProductListItem[],
  total = items.length
): Paginated<ProductListItem> {
  return { items, total, page: 1, page_size: 20 };
}

function renderPage(showToast = vi.fn()) {
  return renderWithProviders(<AdminProductsPage />, {
    toast: { showToast },
  });
}

function getRow(name: string) {
  // В режиме редактирования имя живёт в value инпута, а не в тексте.
  const cell = screen.queryByDisplayValue(name) ?? screen.getByText(name);
  const row = cell.closest("tr");
  if (row === null) throw new Error("row not found");
  return row;
}

beforeEach(() => {
  mList.mockReset().mockResolvedValue(makePage([PRODUCT]));
  mCreate.mockReset();
  mUpdate.mockReset();
  mDelete.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminProductsPage", () => {
  it("loading → «Загрузка…»", () => {
    mList.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("ошибка загрузки показывается", async () => {
    mList.mockRejectedValue(new Error("list boom"));
    renderPage();

    expect(await screen.findByText("list boom")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("пустой список → «Товаров нет.»", async () => {
    mList.mockResolvedValue(makePage([], 0));
    renderPage();

    expect(await screen.findByText("Товаров нет.")).toBeInTheDocument();
  });

  it("рендерит строку товара с ценой и кнопками", async () => {
    renderPage();

    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/1\s*999,99\s*₽/)).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Редактировать" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Удалить" })).toBeInTheDocument();
  });

  it("поиск сбрасывает страницу на 1 и передаёт q", async () => {
    mList.mockResolvedValue(makePage([PRODUCT], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3");

    await userEvent.setup().click(
      screen.getByRole("button", { name: /Следующая/ })
    );
    expect(await screen.findByText("Страница 2 из 3")).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText("Поиск по имени/описанию/категории"),
      { target: { value: "lap" } }
    );

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, q: "lap" })
      )
    );
  });

  it("фильтр статуса сбрасывает страницу и передаёт status", async () => {
    mList.mockResolvedValue(makePage([PRODUCT], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3");

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "out_of_stock" },
    });

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, status: "out_of_stock" })
      )
    );
  });

  it("пагинация: вперёд/назад и границы", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([PRODUCT], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3");

    expect(screen.getByRole("button", { name: /Предыдущая/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Следующая/ }));
    expect(await screen.findByText("Страница 2 из 3")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Предыдущая/ })
    ).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /Следующая/ }));
    expect(await screen.findByText("Страница 3 из 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Следующая/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Предыдущая/ }));
    expect(await screen.findByText("Страница 2 из 3")).toBeInTheDocument();
  });

  it("форма создания открывается и закрывается", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "+ Создать" }));
    expect(screen.getByPlaceholderText("Название")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByPlaceholderText("Название")).not.toBeInTheDocument();
  });

  it("создание без обязательных полей → error-toast, API не вызван", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "+ Создать" }));
    const form = screen
      .getByRole("button", { name: "Создать" })
      .closest("form");
    fireEvent.submit(form as HTMLFormElement);

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith(
        "Заполните имя, цену и категорию",
        "error"
      )
    );
    expect(mCreate).not.toHaveBeenCalled();
  });

  it("создание: триминг, description «—», toast, reload и закрытие формы", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCreate.mockResolvedValue({} as never);
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "+ Создать" }));
    fireEvent.change(screen.getByPlaceholderText("Название"), {
      target: { value: "  New Product  " },
    });
    fireEvent.change(screen.getByPlaceholderText("Цена (напр. 1999.99)"), {
      target: { value: " 1500.00 " },
    });
    fireEvent.change(screen.getByPlaceholderText("ID категории"), {
      target: { value: "5" },
    });
    fireEvent.change(screen.getByPlaceholderText("Описание (опц.)"), {
      target: { value: "   " },
    });
    await user.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() =>
      expect(mCreate).toHaveBeenCalledWith({
        name: "New Product",
        description: "—",
        cost: "1500.00",
        category_id: 5,
        status: "available",
      })
    );
    expect(showToast).toHaveBeenCalledWith("Товар создан", "success");
    expect(screen.queryByPlaceholderText("Название")).not.toBeInTheDocument();
    expect(mList).toHaveBeenCalledTimes(2);
  });

  it("ошибка создания → error-toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCreate.mockRejectedValue(new Error("create boom"));
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "+ Создать" }));
    fireEvent.change(screen.getByPlaceholderText("Название"), {
      target: { value: "New" },
    });
    fireEvent.change(screen.getByPlaceholderText("Цена (напр. 1999.99)"), {
      target: { value: "10.00" },
    });
    fireEvent.change(screen.getByPlaceholderText("ID категории"), {
      target: { value: "1" },
    });
    await user.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("create boom", "error")
    );
  });

  it("редактирование сохраняет и обновляет строку", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const updated: ProductListItem = {
      ...PRODUCT,
      name: "New Name",
      cost: "2000.00",
      status: "out_of_stock",
    };
    mList
      .mockResolvedValueOnce(makePage([PRODUCT]))
      .mockResolvedValueOnce(makePage([updated]));
    mUpdate.mockResolvedValue({} as never);
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Редактировать" }));
    const row = getRow("Laptop");
    fireEvent.change(within(row).getByDisplayValue("Laptop"), {
      target: { value: "New Name" },
    });
    fireEvent.change(within(row).getByDisplayValue("1999.99"), {
      target: { value: "2000.00" },
    });
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "out_of_stock" },
    });
    await user.click(within(row).getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(mUpdate).toHaveBeenCalledWith(1, {
        name: "New Name",
        cost: "2000.00",
        status: "out_of_stock",
      })
    );
    expect(showToast).toHaveBeenCalledWith("Товар обновлён", "success");
    expect(await screen.findByText("New Name")).toBeInTheDocument();
    expect(screen.getByText(/2\s*000,00\s*₽/)).toBeInTheDocument();
  });

  it("отмена редактирования не вызывает API", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Редактировать" }));
    const row = getRow("Laptop");
    await user.click(within(row).getByRole("button", { name: "Отмена" }));

    expect(mUpdate).not.toHaveBeenCalled();
    expect(screen.getByText("Laptop")).toBeInTheDocument();
  });

  it("ошибка обновления → error-toast, режим редактирования остаётся", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mUpdate.mockRejectedValue(new Error("update boom"));
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Редактировать" }));
    const row = getRow("Laptop");
    await user.click(within(row).getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("update boom", "error")
    );
    expect(screen.getByDisplayValue("Laptop")).toBeInTheDocument();
  });

  it("во время сохранения кнопки disabled", async () => {
    const user = userEvent.setup();
    let resolveUpdate: (value: unknown) => void = () => undefined;
    mUpdate.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      }) as never
    );
    renderPage();
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Редактировать" }));
    const row = getRow("Laptop");
    await user.click(within(row).getByRole("button", { name: "Сохранить" }));

    expect(
      within(row).getByRole("button", { name: "Сохранить" })
    ).toBeDisabled();

    resolveUpdate({});
    await waitFor(() =>
      expect(mUpdate).toHaveBeenCalledTimes(1)
    );
  });

  it("удаление с подтверждением: API, info-toast и reload", async () => {
    const user = userEvent.setup();
    const confirmMock = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirmMock);
    const showToast = vi.fn();
    mDelete.mockResolvedValue(undefined);
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(mDelete).toHaveBeenCalledWith(1));
    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith("Товар удалён", "info");
    expect(mList).toHaveBeenCalledTimes(2);
  });

  it("удаление отменено → API не вызван", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    const showToast = vi.fn();
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    expect(mDelete).not.toHaveBeenCalled();
    expect(showToast).not.toHaveBeenCalled();
  });

  it("ошибка удаления → error-toast", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const showToast = vi.fn();
    mDelete.mockRejectedValue(new Error("delete boom"));
    renderPage(showToast);
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("delete boom", "error")
    );
  });
});
