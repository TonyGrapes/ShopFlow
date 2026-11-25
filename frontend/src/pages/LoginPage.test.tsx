import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";

import { LoginPage } from "./LoginPage";
import { renderWithProviders } from "../test/render";
import { ApiError } from "../api/client";
import { resendVerification } from "../api/auth";
import type { UserResponse } from "../types/auth";

// LoginPage импортирует из ../api/auth только resendVerification
// (вызывается в handleResend). Сам login идёт через useAuth().login —
// поэтому мок auth.login в renderWithProviders, а не loginUser здесь.
// vi.mock оставляем как safety net: если компонент случайно дёрнет
// ../api/auth напрямую — тест не пойдёт в сеть.
vi.mock("../api/auth", () => ({
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  logoutUser: vi.fn(),
  fetchMe: vi.fn(),
  refreshSession: vi.fn(),
  resendVerification: vi.fn(),
  verifyEmail: vi.fn(),
  verifyEmailOnce: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
}));

const mResend = vi.mocked(resendVerification);

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

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="path">{location.pathname}</div>;
}

function RedirectApp() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="*" element={<LocationProbe />} />
    </Routes>
  );
}

function submitForm() {
  const form = screen
    .getByRole("button", { name: /Войти/i })
    .closest("form");
  if (form === null) throw new Error("form not found");
  fireEvent.submit(form);
}

beforeEach(() => {
  mResend.mockReset();
});

describe("LoginPage", () => {
  it("валидирует email до сабмита", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    // "a@b" проходит HTML5-валидацию input[type=email] (WHATWG допускает
    // domain без TLD), но НЕ проходит наш EMAIL_RE — он требует ".tld".
    await user.type(screen.getByLabelText(/Email/i), "a@b");
    await user.type(screen.getByLabelText(/Пароль/i), "some-password");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    expect(
      await screen.findByText("Введите корректный email")
    ).toBeInTheDocument();
  });

  it("пустой пароль → ошибка валидации", async () => {
    renderWithProviders(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/Email/i), {
      target: { value: "user@example.com" },
    });

    submitForm();

    expect(await screen.findByText("Введите пароль")).toBeInTheDocument();
  });

  it("показывает detail из ApiError при неверных учётных данных", async () => {
    const user = userEvent.setup();
    const loginReject = vi.fn().mockRejectedValueOnce(
      new ApiError(401, "Invalid credentials")
    );
    renderWithProviders(<LoginPage />, {
      auth: { login: loginReject },
    });

    await user.type(screen.getByLabelText(/Email/i), "user@example.com");
    await user.type(screen.getByLabelText(/Пароль/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    await waitFor(() =>
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument()
    );
    expect(loginReject).toHaveBeenCalledTimes(1);
    expect(loginReject).toHaveBeenCalledWith({
      email: "user@example.com",
      password: "wrong-password",
    });
  });

  it("generic-ошибка логина → текст через getErrorMessage", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockRejectedValue(new Error("net down"));
    renderWithProviders(<LoginPage />, { auth: { login } });

    await user.type(screen.getByLabelText(/Email/i), "user@example.com");
    await user.type(screen.getByLabelText(/Пароль/i), "secret");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    expect(await screen.findByText("net down")).toBeInTheDocument();
  });

  it("успешный логин: email trim + переход на /", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <RedirectApp />,
      { auth: { login }, route: "/login" }
    );

    fireEvent.change(screen.getByLabelText(/Email/i), {
      target: { value: "  user@example.com  " },
    });
    fireEvent.change(screen.getByLabelText(/Пароль/i), {
      target: { value: "secret" },
    });

    submitForm();

    await waitFor(() =>
      expect(login).toHaveBeenCalledWith({
        email: "user@example.com",
        password: "secret",
      })
    );
    await waitFor(() =>
      expect(screen.getByTestId("path").textContent).toBe("/")
    );
  });

  it("loading=true при наличии user → форма остаётся", () => {
    renderWithProviders(<LoginPage />, {
      auth: { user: USER, loading: true },
    });

    expect(
      screen.getByRole("button", { name: /Войти/i })
    ).toBeInTheDocument();
  });

  it("user уже залогинен → редирект на /", async () => {
    renderWithProviders(
      <RedirectApp />,
      { auth: { user: USER }, route: "/login" }
    );

    await waitFor(() =>
      expect(screen.getByTestId("path").textContent).toBe("/")
    );
    expect(
      screen.queryByRole("button", { name: /Войти/i })
    ).not.toBeInTheDocument();
  });

  it("user залогинен → редирект на location.state.from", async () => {
    renderWithProviders(
      <RedirectApp />,
      {
        auth: { user: USER },
        route: "/login",
        routeState: { from: "/checkout" },
      }
    );

    await waitFor(() =>
      expect(screen.getByTestId("path").textContent).toBe("/checkout")
    );
  });

  it("location.state.from не строка → редирект на /", async () => {
    renderWithProviders(
      <RedirectApp />,
      {
        auth: { user: USER },
        route: "/login",
        routeState: { from: 42 },
      }
    );

    await waitFor(() =>
      expect(screen.getByTestId("path").textContent).toBe("/")
    );
  });

  it("403 → подсказка верификации и повторная отправка письма", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const login = vi
      .fn()
      .mockRejectedValue(new ApiError(403, "Email not verified"));
    mResend.mockResolvedValue({ message: "sent" });
    renderWithProviders(<LoginPage />, {
      auth: { login },
      toast: { showToast },
    });

    await user.type(screen.getByLabelText(/Email/i), "user@example.com");
    await user.type(screen.getByLabelText(/Пароль/i), "secret");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    expect(await screen.findByText("Email not verified")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /Отправить письмо повторно/i })
    );

    await waitFor(() =>
      expect(mResend).toHaveBeenCalledWith({ email: "user@example.com" })
    );
    expect(showToast).toHaveBeenCalledWith(
      "Если адрес зарегистрирован и не подтверждён, письмо отправлено.",
      "info"
    );
  });

  it("ошибка повторной отправки → toast error", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const login = vi
      .fn()
      .mockRejectedValue(new ApiError(403, "Email not verified"));
    mResend.mockRejectedValue(new Error("resend fail"));
    renderWithProviders(<LoginPage />, {
      auth: { login },
      toast: { showToast },
    });

    await user.type(screen.getByLabelText(/Email/i), "user@example.com");
    await user.type(screen.getByLabelText(/Пароль/i), "secret");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    await user.click(
      await screen.findByRole("button", {
        name: /Отправить письмо повторно/i,
      })
    );

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("resend fail", "error")
    );
  });

  it("повторная отправка с невалидным email → ошибка без запроса", async () => {
    const user = userEvent.setup();
    const login = vi
      .fn()
      .mockRejectedValue(new ApiError(403, "Email not verified"));
    renderWithProviders(<LoginPage />, { auth: { login } });

    const emailInput = screen.getByLabelText(/Email/i);
    await user.type(emailInput, "user@example.com");
    await user.type(screen.getByLabelText(/Пароль/i), "secret");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    await user.clear(emailInput);
    await user.type(emailInput, "a@b");
    await user.click(
      await screen.findByRole("button", {
        name: /Отправить письмо повторно/i,
      })
    );

    expect(
      await screen.findByText("Введите корректный email")
    ).toBeInTheDocument();
    expect(mResend).not.toHaveBeenCalled();
  });
});
