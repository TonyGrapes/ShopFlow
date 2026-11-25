import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FavoritesProvider } from "./FavoritesProvider";
import { useFavorites } from "../hooks/useFavorites";
import type { FavoritesContextValue } from "./favoritesContext";
import {
  addFavorite,
  fetchFavorites,
  removeFavorite,
} from "../api/favorites";
import type { FavoriteResponse } from "../types/favorite";
import type { UserResponse } from "../types/auth";

const { authState } = vi.hoisted(() => ({
  authState: { user: null as UserResponse | null, loading: false },
}));

vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));

vi.mock("../api/favorites", () => ({
  fetchFavorites: vi.fn(),
  addFavorite: vi.fn(),
  removeFavorite: vi.fn(),
}));

const mFetch = vi.mocked(fetchFavorites);
const mAdd = vi.mocked(addFavorite);
const mRemove = vi.mocked(removeFavorite);

const USER: UserResponse = {
  public_id: "u-1",
  email: "user@example.com",
  first_name: "Ann",
  last_name: "Lee",
  phone_number: "+10000000000",
  role: "customer",
  status: "active",
  is_email_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

const FAV: FavoriteResponse = {
  id: 1,
  product_id: 7,
  product_name: "Laptop",
  cover_url: null,
  cost: "1000.00",
  status: "available",
  created_at: "2026-01-02T00:00:00Z",
};

const FAV2: FavoriteResponse = {
  ...FAV,
  id: 2,
  product_id: 8,
  product_name: "Mouse",
};

let ctx: FavoritesContextValue;

function Capture() {
  ctx = useFavorites();
  return null;
}

function renderProvider() {
  return render(
    <FavoritesProvider>
      <Capture />
    </FavoritesProvider>
  );
}

beforeEach(() => {
  [mFetch, mAdd, mRemove].forEach((m) => m.mockReset());
  mFetch.mockResolvedValue([]);
  authState.user = null;
  authState.loading = false;
});

afterEach(() => {
  cleanup();
});

describe("initial load", () => {
  it("authLoading=true → не грузит избранное", () => {
    authState.loading = true;
    renderProvider();

    expect(mFetch).not.toHaveBeenCalled();
    expect(ctx.loading).toBe(false);
  });

  it("гость: пустой список, без запроса", () => {
    renderProvider();

    expect(mFetch).not.toHaveBeenCalled();
    expect(ctx.favorites).toEqual([]);
    expect(ctx.loading).toBe(false);
    expect(ctx.error).toBeNull();
  });

  it("авторизован: загружает избранное", async () => {
    authState.user = USER;
    mFetch.mockResolvedValue([FAV]);
    renderProvider();

    await waitFor(() => expect(ctx.loading).toBe(false));

    expect(mFetch).toHaveBeenCalledTimes(1);
    expect(ctx.favorites).toEqual([FAV]);
    expect(ctx.error).toBeNull();
  });

  it("ошибка загрузки → error", async () => {
    authState.user = USER;
    mFetch.mockRejectedValue(new Error("fav fail"));
    renderProvider();

    await waitFor(() => expect(ctx.error).toBe("fav fail"));

    expect(ctx.loading).toBe(false);
    expect(ctx.favorites).toEqual([]);
  });

  it("гость → пользователь: перезагружает", async () => {
    const { rerender } = renderProvider();
    expect(mFetch).not.toHaveBeenCalled();

    authState.user = USER;
    rerender(
      <FavoritesProvider>
        <Capture />
      </FavoritesProvider>
    );

    await waitFor(() => expect(mFetch).toHaveBeenCalledTimes(1));
  });

  it("отмена до завершения fetch не обновляет состояние", async () => {
    authState.user = USER;
    let resolveFetch!: (value: FavoriteResponse[]) => void;
    mFetch.mockReturnValue(
      new Promise<FavoriteResponse[]>((resolve) => {
        resolveFetch = resolve;
      })
    );

    const { unmount } = renderProvider();
    unmount();

    await act(async () => {
      resolveFetch([FAV]);
    });

    expect(ctx.favorites).toEqual([]);
  });
});

describe("refreshFavorites", () => {
  it("успех: обновляет список", async () => {
    authState.user = USER;
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    mFetch.mockResolvedValueOnce([FAV2]);
    await act(async () => {
      await ctx.refreshFavorites();
    });

    expect(ctx.favorites).toEqual([FAV2]);
    expect(ctx.loading).toBe(false);
  });

  it("ошибка: ставит error и пробрасывает", async () => {
    authState.user = USER;
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    mFetch.mockRejectedValueOnce(new Error("refresh failed"));
    await act(async () => {
      await expect(ctx.refreshFavorites()).rejects.toThrow("refresh failed");
    });

    expect(ctx.error).toBe("refresh failed");
    expect(ctx.loading).toBe(false);
  });
});

describe("isFavorite / isPending", () => {
  it("отражают текущее состояние", async () => {
    authState.user = USER;
    mFetch.mockResolvedValue([FAV]);
    renderProvider();
    await waitFor(() => expect(ctx.favorites).toEqual([FAV]));

    expect(ctx.isFavorite(7)).toBe(true);
    expect(ctx.isFavorite(9)).toBe(false);
    expect(ctx.isPending(7)).toBe(false);
  });
});

describe("toggleFavorite", () => {
  it("гость: бросает ошибку авторизации", async () => {
    renderProvider();

    await act(async () => {
      await expect(ctx.toggleFavorite(7)).rejects.toThrow(
        "Требуется авторизация"
      );
    });

    expect(mAdd).not.toHaveBeenCalled();
    expect(mRemove).not.toHaveBeenCalled();
  });

  it("удаление существующего: оптимистично убирает", async () => {
    authState.user = USER;
    mFetch.mockResolvedValue([FAV]);
    renderProvider();
    await waitFor(() => expect(ctx.favorites).toEqual([FAV]));

    mRemove.mockResolvedValue(undefined);
    await act(async () => {
      await ctx.toggleFavorite(7);
    });

    expect(mRemove).toHaveBeenCalledWith(7);
    expect(ctx.favorites).toEqual([]);
    expect(ctx.isFavorite(7)).toBe(false);
  });

  it("удаление с ошибкой: откатывает список", async () => {
    authState.user = USER;
    mFetch.mockResolvedValue([FAV]);
    renderProvider();
    await waitFor(() => expect(ctx.favorites).toEqual([FAV]));

    mRemove.mockRejectedValue(new Error("rm fail"));
    await act(async () => {
      await expect(ctx.toggleFavorite(7)).rejects.toThrow("rm fail");
    });

    expect(ctx.favorites).toEqual([FAV]);
    expect(ctx.isPending(7)).toBe(false);
  });

  it("добавление нового: prepend и сброс pending", async () => {
    authState.user = USER;
    mFetch.mockResolvedValue([FAV]);
    renderProvider();
    await waitFor(() => expect(ctx.favorites).toEqual([FAV]));

    mAdd.mockResolvedValue(FAV2);
    await act(async () => {
      await ctx.toggleFavorite(8);
    });

    expect(mAdd).toHaveBeenCalledWith({ product_id: 8 });
    expect(ctx.favorites).toEqual([FAV2, FAV]);
    expect(ctx.isPending(8)).toBe(false);
  });

  it("pending: повторный вызов игнорируется", async () => {
    authState.user = USER;
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    let resolveAdd!: (value: FavoriteResponse) => void;
    mAdd.mockReturnValue(
      new Promise<FavoriteResponse>((resolve) => {
        resolveAdd = resolve;
      })
    );

    let first!: Promise<void>;
    act(() => {
      first = ctx.toggleFavorite(7);
    });
    expect(ctx.isPending(7)).toBe(true);

    let second!: Promise<void>;
    act(() => {
      second = ctx.toggleFavorite(7);
    });
    expect(mAdd).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveAdd(FAV);
      await Promise.all([first, second]);
    });

    expect(ctx.favorites).toEqual([FAV]);
    expect(ctx.isPending(7)).toBe(false);
  });
});

describe("useFavorites", () => {
  it("вне FavoritesProvider бросает", () => {
    function Orphan() {
      useFavorites();
      return null;
    }
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Orphan />)).toThrow(
      "useFavorites must be used within FavoritesProvider"
    );

    errSpy.mockRestore();
  });
});
