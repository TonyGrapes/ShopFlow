import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useRecentlyViewed } from "./useRecentlyViewed";

const KEY = "shopflow.recently-viewed";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("useRecentlyViewed", () => {
  it("пусто без сохранённых данных", () => {
    const { result } = renderHook(() => useRecentlyViewed());
    expect(result.current.ids).toEqual([]);
  });

  it("читает валидные id из localStorage", () => {
    localStorage.setItem(KEY, JSON.stringify([3, 1, 2]));
    const { result } = renderHook(() => useRecentlyViewed());
    expect(result.current.ids).toEqual([3, 1, 2]);
  });

  it("игнорирует битый JSON и не-массивы", () => {
    localStorage.setItem(KEY, "{not json");
    const first = renderHook(() => useRecentlyViewed());
    expect(first.result.current.ids).toEqual([]);

    localStorage.setItem(KEY, JSON.stringify({ ids: [1] }));
    const second = renderHook(() => useRecentlyViewed());
    expect(second.result.current.ids).toEqual([]);
  });

  it("отбрасывает нецелые id и ограничивает 8", () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([1, "x", 2.5, 2, 3, 4, 5, 6, 7, 8, 9])
    );
    const { result } = renderHook(() => useRecentlyViewed());
    expect(result.current.ids).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("push добавляет в начало, дедуплицирует и сохраняет", () => {
    const { result } = renderHook(() => useRecentlyViewed());

    act(() => result.current.push(1));
    act(() => result.current.push(2));
    act(() => result.current.push(1));

    expect(result.current.ids).toEqual([1, 2]);
    expect(JSON.parse(localStorage.getItem(KEY) ?? "[]")).toEqual([1, 2]);
  });

  it("push ограничивает историю 8 элементами", () => {
    const { result } = renderHook(() => useRecentlyViewed());

    act(() => {
      for (let id = 1; id <= 9; id += 1) result.current.push(id);
    });

    expect(result.current.ids).toEqual([9, 8, 7, 6, 5, 4, 3, 2]);
  });

  it("clear очищает state и storage", () => {
    localStorage.setItem(KEY, JSON.stringify([1]));
    const { result } = renderHook(() => useRecentlyViewed());

    act(() => result.current.clear());

    expect(result.current.ids).toEqual([]);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("не падает, если storage недоступен", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("denied");
    });

    const { result } = renderHook(() => useRecentlyViewed());

    expect(() => act(() => result.current.push(1))).not.toThrow();
    expect(result.current.ids).toEqual([1]);
    expect(() => act(() => result.current.clear())).not.toThrow();
    expect(result.current.ids).toEqual([]);
  });
});
