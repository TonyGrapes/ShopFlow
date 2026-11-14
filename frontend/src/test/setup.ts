// Глобальный setup для всех тестов.
// - jest-dom matchers (toBeInTheDocument и т.п.) для expect
// - заглушки браузерных API, которые jsdom не реализует
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// prefers-color-scheme / responsive queries: jsdom не реализует matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// window.scrollTo: вызывается в CatalogPage / Pagination при смене страницы
Object.defineProperty(window, "scrollTo", {
  writable: true,
  value: vi.fn(),
});

// crypto.randomUUID: используется в CheckoutPage / OrderDetailPage
if (typeof globalThis.crypto?.randomUUID !== "function") {
  Object.defineProperty(globalThis.crypto, "randomUUID", {
    value: () => "00000000-0000-0000-0000-000000000000",
    writable: true,
  });
}

// URL.createObjectURL / revokeObjectURL: используется в downloadDashboardCsv
if (typeof URL.createObjectURL !== "function") {
  Object.defineProperty(URL, "createObjectURL", {
    value: vi.fn(() => "blob:mock"),
    writable: true,
  });
}
if (typeof URL.revokeObjectURL !== "function") {
  Object.defineProperty(URL, "revokeObjectURL", {
    value: vi.fn(),
    writable: true,
  });
}