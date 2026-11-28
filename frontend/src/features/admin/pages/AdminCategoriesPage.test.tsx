import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdminCategoriesPage } from "./AdminCategoriesPage";
import { renderWithProviders } from "../../../test/render";
import type { Category } from "../../../types/category";

vi.mock("../../../api/categories", () => ({
  fetchCategories: vi.fn(),
  fetchCategoryTree: vi.fn(),
}));
vi.mock("../../../api/admin", () => ({
  createCategory: vi.fn(),
  deleteCategory: vi.fn(),
}));

import { fetchCategories } from "../../../api/categories";
import { createCategory, deleteCategory } from "../../../api/admin";

const mFetch = vi.mocked(fetchCategories);
const mCreate = vi.mocked(createCategory);
const mDelete = vi.mocked(deleteCategory);

const ROOT: Category = {
  id: 1,
  category_name: "Electronics",
  path: "1",
  parent_id: null,
};

const CHILD: Category = {
  id: 2,
  category_name: "Laptops",
  path: "1.2",
  parent_id: 1,
};

function renderPage(showToast = vi.fn()) {
  return renderWithProviders(<AdminCategoriesPage />, {
    toast: { showToast },
  });
}

function getCreateForm() {
  const form = screen
    .getByRole("button", { name: "Создать" })
    .closest("form");
  if (form === null) throw new Error("form not found");
  return form;
}

beforeEach(() => {
  mFetch.mockReset().mockResolvedValue([ROOT, CHILD]);
  mCreate.mockReset();
  mDelete.mockReset();
});

describe("AdminCategoriesPage", () => {
  it("loading → «Загрузка…»", () => {
    mFetch.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("ошибка загрузки показывается без таблицы", async () => {
    mFetch.mockRejectedValue(new Error("categories boom"));
    renderPage();

    expect(await screen.findByText("categories boom")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("пустой список: только корневая опция и нет кнопок удаления", async () => {
    mFetch.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Удалить" })
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Родительская категория")).getAllByRole(
        "option"
      )
    ).toHaveLength(1);
  });

  it("рендерит строки дерева и опции родителя", async () => {
    renderPage();

    expect(await screen.findAllByText("Electronics")).not.toHaveLength(0);
    expect(screen.getAllByText("Laptops").length).toBeGreaterThan(0);
    expect(screen.getByText("1.2")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();

    const select = screen.getByLabelText("Родительская категория");
    expect(within(select).getByRole("option", { name: "Electronics" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "Laptops" })).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Удалить" })
    ).toHaveLength(2);
  });

  it("пустое имя не отправляет запрос", async () => {
    const showToast = vi.fn();
    renderPage(showToast);
    await screen.findAllByText("Electronics");

    fireEvent.submit(getCreateForm());

    expect(mCreate).not.toHaveBeenCalled();
    expect(showToast).not.toHaveBeenCalled();
  });

  it("создание корневой: триминг, toast, очистка и refetch", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCreate.mockResolvedValue({ ...ROOT, id: 3 });
    renderPage(showToast);
    await screen.findAllByText("Electronics");

    const input = screen.getByLabelText("Название категории");
    fireEvent.change(input, { target: { value: "  Audio  " } });
    await user.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() =>
      expect(mCreate).toHaveBeenCalledWith({ category_name: "Audio" })
    );
    expect(showToast).toHaveBeenCalledWith("Категория создана", "success");
    expect(input).toHaveValue("");
    await waitFor(() => expect(mFetch).toHaveBeenCalledTimes(2));
  });

  it("создание дочерней передаёт parent_id", async () => {
    const user = userEvent.setup();
    mCreate.mockResolvedValue({ ...CHILD, id: 3 });
    renderPage();
    await screen.findAllByText("Electronics");

    fireEvent.change(screen.getByLabelText("Название категории"), {
      target: { value: "Phones" },
    });
    fireEvent.change(screen.getByLabelText("Родительская категория"), {
      target: { value: "1" },
    });
    await user.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() =>
      expect(mCreate).toHaveBeenCalledWith({
        category_name: "Phones",
        parent_id: 1,
      })
    );
  });

  it("ошибка создания → error-toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mCreate.mockRejectedValue(new Error("create cat boom"));
    renderPage(showToast);
    await screen.findAllByText("Electronics");

    fireEvent.change(screen.getByLabelText("Название категории"), {
      target: { value: "Audio" },
    });
    await user.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("create cat boom", "error")
    );
  });

  it("во время создания кнопки disabled", async () => {
    const user = userEvent.setup();
    let resolveCreate: (value: Category) => void = () => undefined;
    mCreate.mockReturnValue(
      new Promise<Category>((resolve) => {
        resolveCreate = resolve;
      })
    );
    renderPage();
    await screen.findAllByText("Electronics");

    fireEvent.change(screen.getByLabelText("Название категории"), {
      target: { value: "Audio" },
    });
    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(screen.getByRole("button", { name: "Создать" })).toBeDisabled();
    expect(
      screen.getAllByRole("button", { name: "Удалить" })[0]
    ).toBeDisabled();

    resolveCreate(ROOT);
    await waitFor(() => expect(mFetch).toHaveBeenCalledTimes(2));
  });

  it("удаление: API, toast и refetch", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mDelete.mockResolvedValue(undefined);
    renderPage(showToast);
    await screen.findAllByText("Electronics");

    await user.click(screen.getAllByRole("button", { name: "Удалить" })[0]);

    await waitFor(() => expect(mDelete).toHaveBeenCalledWith(1));
    expect(showToast).toHaveBeenCalledWith("Категория удалена", "success");
    await waitFor(() => expect(mFetch).toHaveBeenCalledTimes(2));
  });

  it("ошибка удаления → error-toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mDelete.mockRejectedValue(new Error("delete cat boom"));
    renderPage(showToast);
    await screen.findAllByText("Electronics");

    await user.click(screen.getAllByRole("button", { name: "Удалить" })[1]);

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("delete cat boom", "error")
    );
  });
});
