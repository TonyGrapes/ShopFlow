import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { ProductPage } from "./ProductPage";
import { renderWithProviders } from "../test/render";
import { fetchProduct } from "../api/products";
import { ApiError } from "../api/client";
import type { ProductResponse } from "../types/product";

vi.mock("../api/products", () => ({ fetchProduct: vi.fn() }));

const mFetch = vi.mocked(fetchProduct);

const PRODUCT: ProductResponse = {
  id: 1,
  name: "Laptop",
  description: "Fast laptop",
  cost: "1000.00",
  category_id: 1,
  status: "available",
  category: { id: 1, category_name: "Electronics" },
  images: [
    { id: 1, url: "https://cdn.example/1.png" },
    { id: 2, url: "https://cdn.example/2.png" },
  ],
  created_at: null,
  updated_at: null,
};

function renderProduct(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/products/:id" element={<ProductPage />} />
    </Routes>,
    { route: `/products/${id}` }
  );
}

beforeEach(() => {
  mFetch.mockReset();
});

describe("ProductPage", () => {
  it("показывает данные товара и переключает изображения", async () => {
    const user = userEvent.setup();
    mFetch.mockResolvedValue(PRODUCT);
    renderProduct("1");

    expect(
      await screen.findByRole("heading", { name: "Laptop" })
    ).toBeInTheDocument();
    expect(mFetch).toHaveBeenCalledWith(1);
    expect(screen.getByText("1000.00 ₽")).toBeInTheDocument();
    expect(screen.getByText("В наличии")).toBeInTheDocument();
    expect(
      screen.getByText("Категория: Electronics")
    ).toBeInTheDocument();
    expect(screen.getByText("Fast laptop")).toBeInTheDocument();

    const mainImage = screen.getByAltText("Laptop");
    expect(mainImage).toHaveAttribute("src", "https://cdn.example/1.png");

    await user.click(screen.getByRole("button", { name: "Laptop 2" }));

    expect(screen.getByAltText("Laptop")).toHaveAttribute(
      "src",
      "https://cdn.example/2.png"
    );
  });

  it("без изображений → заглушка", async () => {
    mFetch.mockResolvedValue({ ...PRODUCT, images: [] });
    renderProduct("1");

    expect(await screen.findByText("Нет изображений")).toBeInTheDocument();
  });

  it("одно изображение → без миниатюр", async () => {
    mFetch.mockResolvedValue({
      ...PRODUCT,
      images: [{ id: 1, url: "https://cdn.example/1.png" }],
    });
    renderProduct("1");

    await screen.findByAltText("Laptop");
    expect(screen.queryByAltText("Laptop 1")).not.toBeInTheDocument();
  });

  it("нет категории → строка категории скрыта", async () => {
    mFetch.mockResolvedValue({ ...PRODUCT, category: null });
    renderProduct("1");

    await screen.findByRole("heading", { name: "Laptop" });
    expect(screen.queryByText(/Категория:/)).not.toBeInTheDocument();
  });

  it("статус out_of_stock → кнопка недоступна", async () => {
    mFetch.mockResolvedValue({ ...PRODUCT, status: "out_of_stock" });
    renderProduct("1");

    await screen.findByRole("heading", { name: "Laptop" });
    expect(screen.getAllByText("Нет в наличии").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Нет в наличии" })
    ).toBeDisabled();
  });

  it("статус discontinued → подпись", async () => {
    mFetch.mockResolvedValue({ ...PRODUCT, status: "discontinued" });
    renderProduct("1");

    expect(
      await screen.findByText("Снят с производства")
    ).toBeInTheDocument();
  });

  it("404 → «Товар не найден»", async () => {
    mFetch.mockRejectedValue(new ApiError(404, "Not found"));
    renderProduct("1");

    expect(await screen.findByText(/Товар не найден/)).toBeInTheDocument();
  });

  it("прочий ApiError → status + detail", async () => {
    mFetch.mockRejectedValue(new ApiError(500, "Server error"));
    renderProduct("1");

    expect(
      await screen.findByText(/500: Server error/)
    ).toBeInTheDocument();
  });

  it("обычная Error → сообщение", async () => {
    mFetch.mockRejectedValue(new Error("net down"));
    renderProduct("1");

    expect(await screen.findByText(/net down/)).toBeInTheDocument();
  });

  it("не-Error → «Неизвестная ошибка»", async () => {
    mFetch.mockRejectedValue("weird");
    renderProduct("1");

    expect(
      await screen.findByText(/Неизвестная ошибка/)
    ).toBeInTheDocument();
  });

  it("некорректный id → ошибка без запроса", async () => {
    renderProduct("abc");

    expect(
      await screen.findByText(/Некорректный ID товара/)
    ).toBeInTheDocument();
    expect(mFetch).not.toHaveBeenCalled();
  });

  it("loading → LoadingState", async () => {
    let resolve!: (value: ProductResponse) => void;
    mFetch.mockReturnValue(
      new Promise<ProductResponse>((r) => {
        resolve = r;
      })
    );
    renderProduct("1");

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();

    await act(async () => {
      resolve(PRODUCT);
    });
  });

  it("product === null без loading/error → пустой вывод", async () => {
    mFetch.mockResolvedValue(null as unknown as ProductResponse);
    const { container } = renderProduct("1");

    await waitFor(() => expect(mFetch).toHaveBeenCalledWith(1));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
