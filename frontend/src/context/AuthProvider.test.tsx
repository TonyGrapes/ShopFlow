import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "../hooks/useAuth";
import type { AuthContextValue } from "./authContext";
import {
  fetchMe,
  loginUser,
  logoutUser,
  registerUser,
} from "../api/auth";
import {
  refreshAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
} from "../api/session";
import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  UserResponse,
} from "../types/auth";

const { navigateMock, showToastMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  showToastMock: vi.fn(),
}));

vi.mock("../api/auth", () => ({
  fetchMe: vi.fn(),
  loginUser: vi.fn(),
  logoutUser: vi.fn(),
  registerUser: vi.fn(),
}));

vi.mock("../api/session", () => ({
  refreshAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../hooks/useToast", () => ({
  useToast: () => ({ showToast: showToastMock }),
}));

const mFetchMe = vi.mocked(fetchMe);
const mLogin = vi.mocked(loginUser);
const mLogout = vi.mocked(logoutUser);
const mRegister = vi.mocked(registerUser);
const mRefresh = vi.mocked(refreshAccessToken);
const mSetToken = vi.mocked(setAccessToken);
const mSetHandler = vi.mocked(setUnauthorizedHandler);

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

const TOKENS: TokenResponse = {
  access_token: "tok",
  token_type: "bearer",
  expires_in: 60,
};

const LOGIN: LoginRequest = { email: "user@example.com", password: "secret" };

const REGISTER: RegisterRequest = {
  email: "new@example.com",
  password: "secret",
  first_name: "New",
  last_name: "User",
  phone_number: "+10000000001",
};

let ctx: AuthContextValue;

function Capture() {
  ctx = useAuth();
  return null;
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Capture />
    </AuthProvider>
  );
}

function getUnauthorizedHandler(): () => void {
  return mSetHandler.mock.calls[0][0] as () => void;
}

beforeEach(() => {
  [
    mFetchMe,
    mLogin,
    mLogout,
    mRegister,
    mRefresh,
    mSetToken,
    mSetHandler,
    navigateMock,
    showToastMock,
  ].forEach((m) => m.mockReset());
  // По умолчанию — гость: refresh-cookie отсутствует.
  mRefresh.mockResolvedValue(null);
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  cleanup();
});

describe("bootstrap", () => {
  it("гость: refresh=null → loading=false, user=null, fetchMe не зовётся", async () => {
    renderProvider();

    await waitFor(() => expect(ctx.loading).toBe(false));

    expect(ctx.user).toBeNull();
    expect(ctx.isAuthenticated).toBe(false);
    expect(mRefresh).toHaveBeenCalledTimes(1);
    expect(mFetchMe).not.toHaveBeenCalled();
  });

  it("восстанавливает сессию: refresh → fetchMe → user", async () => {
    mRefresh.mockResolvedValue(TOKENS);
    mFetchMe.mockResolvedValue(USER);

    renderProvider();

    await waitFor(() => expect(ctx.user).toEqual(USER));

    expect(ctx.loading).toBe(false);
    expect(ctx.isAuthenticated).toBe(true);
    expect(mFetchMe).toHaveBeenCalledTimes(1);
  });

  it("refresh падает → гость без ошибки", async () => {
    mRefresh.mockRejectedValue(new Error("network"));

    renderProvider();

    await waitFor(() => expect(ctx.loading).toBe(false));

    expect(ctx.user).toBeNull();
  });

  it("fetchMe падает после refresh → гость", async () => {
    mRefresh.mockResolvedValue(TOKENS);
    mFetchMe.mockRejectedValue(new Error("me failed"));

    renderProvider();

    await waitFor(() => expect(ctx.loading).toBe(false));

    expect(ctx.user).toBeNull();
  });

  it("отмена до завершения refresh не трогает состояние", async () => {
    let resolveRefresh!: (value: TokenResponse | null) => void;
    mRefresh.mockReturnValue(
      new Promise<TokenResponse | null>((resolve) => {
        resolveRefresh = resolve;
      })
    );

    const { unmount } = renderProvider();
    unmount();

    await act(async () => {
      resolveRefresh(null);
    });

    expect(mFetchMe).not.toHaveBeenCalled();
  });
});

describe("unauthorized handler", () => {
  it("на обычном пути: сброс user + toast + redirect на /login", async () => {
    window.history.pushState({}, "", "/cart?promo=1");
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    const handler = getUnauthorizedHandler();
    act(() => handler());

    expect(ctx.user).toBeNull();
    expect(showToastMock).toHaveBeenCalledWith(
      "Сессия истекла. Войдите снова.",
      "error"
    );
    expect(navigateMock).toHaveBeenCalledWith("/login", {
      state: { from: "/cart?promo=1" },
    });
  });

  it.each(["/login", "/register", "/verify-email"])(
    "на %s не показывает toast и не редиректит",
    async (path) => {
      window.history.pushState({}, "", path);
      renderProvider();
      await waitFor(() => expect(ctx.loading).toBe(false));

      act(() => getUnauthorizedHandler()());

      expect(showToastMock).not.toHaveBeenCalled();
      expect(navigateMock).not.toHaveBeenCalled();
    }
  );
});

describe("login", () => {
  it("успех: ставит access-токен и user", async () => {
    mLogin.mockResolvedValue(TOKENS);
    mFetchMe.mockResolvedValue(USER);
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    await act(async () => {
      await ctx.login(LOGIN);
    });

    expect(mLogin).toHaveBeenCalledWith(LOGIN);
    expect(mSetToken).toHaveBeenCalledWith("tok");
    expect(ctx.user).toEqual(USER);
    expect(ctx.isAuthenticated).toBe(true);
  });

  it("fetchMe падает → сбрасывает токен и пробрасывает ошибку", async () => {
    mLogin.mockResolvedValue(TOKENS);
    mFetchMe.mockRejectedValue(new Error("boom"));
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    await act(async () => {
      await expect(ctx.login(LOGIN)).rejects.toThrow("boom");
    });

    expect(mSetToken).toHaveBeenCalledWith("tok");
    expect(mSetToken).toHaveBeenLastCalledWith(null);
    expect(ctx.user).toBeNull();
  });
});

describe("register", () => {
  it("прокидывает данные и возвращает пользователя", async () => {
    mRegister.mockResolvedValue(USER);
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    let result: UserResponse | undefined;
    await act(async () => {
      result = await ctx.register(REGISTER);
    });

    expect(mRegister).toHaveBeenCalledWith(REGISTER);
    expect(result).toEqual(USER);
  });
});

describe("logout", () => {
  it("успех: чистит токен и user", async () => {
    mLogout.mockResolvedValue({ message: "ok" });
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    await act(async () => {
      await ctx.logout();
    });

    expect(mLogout).toHaveBeenCalledTimes(1);
    expect(mSetToken).toHaveBeenCalledWith(null);
    expect(ctx.user).toBeNull();
  });

  it("ошибка сервера: всё равно чистит локальную сессию", async () => {
    mLogout.mockRejectedValue(new Error("offline"));
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    await act(async () => {
      await ctx.logout();
    });

    expect(mSetToken).toHaveBeenCalledWith(null);
    expect(ctx.user).toBeNull();
  });
});

describe("refreshUser", () => {
  it("перезагружает user через fetchMe", async () => {
    mFetchMe.mockResolvedValue(USER);
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    await act(async () => {
      await ctx.refreshUser();
    });

    expect(mFetchMe).toHaveBeenCalledTimes(1);
    expect(ctx.user).toEqual(USER);
  });
});

describe("useAuth", () => {
  it("вне AuthProvider бросает", () => {
    function Orphan() {
      useAuth();
      return null;
    }
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Orphan />)).toThrow(
      "useAuth must be used within AuthProvider"
    );

    errSpy.mockRestore();
  });
});
