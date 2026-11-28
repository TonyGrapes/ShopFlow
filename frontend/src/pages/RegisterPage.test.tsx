import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";

import { RegisterPage } from "./RegisterPage";
import { renderWithProviders } from "../test/render";
import { ApiError } from "../api/client";
import { resendVerification } from "../api/auth";
import type { AuthContextValue } from "../context/authContext";
import type { UserResponse } from "../types/auth";

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
  email: "new@example.com",
  first_name: "Ann",
  last_name: "Lee",
  phone_number: "+7 999 000-00-00",
  role: "customer",
  status: "pending",
  is_email_verified: false,
  created_at: "2026-01-01T00:00:00Z",
};

const RESEND_OK = { message: "ok" };

function PathProbe() {
  const location = useLocation();
  return <div data-testid="path">{location.pathname}</div>;
}

function renderRegister(
  auth: Partial<AuthContextValue> = {},
  showToast = vi.fn()
) {
  return renderWithProviders(
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="*" element={<PathProbe />} />
    </Routes>,
    { route: "/register", auth, toast: { showToast } }
  );
}

function fillForm(
  overrides: Partial<{
    email: string;
    password: string;
    firstName: string;
    lastName: string;
    phone: string;
  }> = {}
) {
  const values = {
    email: "new@example.com",
    password: "password123",
    firstName: "Ann",
    lastName: "Lee",
    phone: "+7 999 000-00-00",
    ...overrides,
  };
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: values.email },
  });
  fireEvent.change(screen.getByLabelText("Пароль"), {
    target: { value: values.password },
  });
  fireEvent.change(screen.getByLabelText("Имя"), {
    target: { value: values.firstName },
  });
  fireEvent.change(screen.getByLabelText("Фамилия"), {
    target: { value: values.lastName },
  });
  fireEvent.change(screen.getByLabelText("Телефон"), {
    target: { value: values.phone },
  });
}

function submitForm() {
  const form = screen
    .getByRole("button", { name: "Создать аккаунт" })
    .closest("form");
  if (form === null) throw new Error("form not found");
  fireEvent.submit(form);
}

beforeEach(() => {
  mResend.mockReset().mockResolvedValue(RESEND_OK);
});

describe("RegisterPage", () => {
  it("гость видит форму регистрации", () => {
    renderRegister({ user: null, loading: false });

    expect(
      screen.getByRole("heading", { name: "Регистрация" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Создать аккаунт" })
    ).toBeInTheDocument();
  });

  it("авторизованный пользователь редиректится на /", () => {
    renderRegister({ user: USER, loading: false });

    expect(screen.getByTestId("path")).toHaveTextContent("/");
  });

  it("некорректный email → ошибка", () => {
    renderRegister({ user: null, loading: false });
    fillForm({ email: "bad" });
    submitForm();

    expect(screen.getByText("Введите корректный email")).toBeInTheDocument();
  });

  it("короткий пароль → ошибка", () => {
    renderRegister({ user: null, loading: false });
    fillForm({ password: "short" });
    submitForm();

    expect(
      screen.getByText("Пароль должен быть от 8 до 128 символов")
    ).toBeInTheDocument();
  });

  it("пустое имя → ошибка", () => {
    renderRegister({ user: null, loading: false });
    fillForm({ firstName: "   " });
    submitForm();

    expect(
      screen.getByText("Имя должно быть от 1 до 100 символов")
    ).toBeInTheDocument();
  });

  it("пустая фамилия → ошибка", () => {
    renderRegister({ user: null, loading: false });
    fillForm({ lastName: "   " });
    submitForm();

    expect(
      screen.getByText("Фамилия должна быть от 1 до 100 символов")
    ).toBeInTheDocument();
  });

  it("некорректный телефон → ошибка", () => {
    renderRegister({ user: null, loading: false });
    fillForm({ phone: "abc" });
    submitForm();

    expect(
      screen.getByText("Введите телефон в формате +7 999 000-00-00")
    ).toBeInTheDocument();
  });

  it("успешная регистрация: register, toast и экран проверки email", async () => {
    const user = userEvent.setup();
    const register = vi.fn().mockResolvedValue(USER);
    const showToast = vi.fn();
    renderRegister({ user: null, loading: false, register }, showToast);

    fillForm({
      email: " new@example.com ",
      firstName: " Ann ",
      lastName: " Lee ",
      phone: " +7 999 000-00-00 ",
    });
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));

    await waitFor(() =>
      expect(register).toHaveBeenCalledWith({
        email: "new@example.com",
        password: "password123",
        first_name: "Ann",
        last_name: "Lee",
        phone_number: "+7 999 000-00-00",
      })
    );
    expect(showToast).toHaveBeenCalledWith(
      "Аккаунт создан. Подтвердите email.",
      "success"
    );
    expect(
      await screen.findByRole("heading", { name: "Проверьте email" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "страницу подтверждения" })
    ).toHaveAttribute("href", "/verify-email");
    expect(
      screen.getByRole("link", { name: "Перейти ко входу" })
    ).toHaveAttribute("href", "/login");
  });

  it("409 от бэкенда → «Этот email уже зарегистрирован»", async () => {
    const user = userEvent.setup();
    const register = vi
      .fn()
      .mockRejectedValue(new ApiError(409, "conflict"));
    renderRegister({ user: null, loading: false, register });

    fillForm();
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));

    expect(
      await screen.findByText("Этот email уже зарегистрирован")
    ).toBeInTheDocument();
  });

  it("прочая ошибка регистрации показывается", async () => {
    const user = userEvent.setup();
    const register = vi.fn().mockRejectedValue(new Error("register boom"));
    renderRegister({ user: null, loading: false, register });

    fillForm();
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));

    expect(await screen.findByText("register boom")).toBeInTheDocument();
  });

  it("во время регистрации кнопка показывает «Создаём...» и disabled", async () => {
    const user = userEvent.setup();
    let resolveRegister: (value: UserResponse) => void = () => undefined;
    const register = vi.fn(
      () =>
        new Promise<UserResponse>((resolve) => {
          resolveRegister = resolve;
        })
    );
    renderRegister({ user: null, loading: false, register });

    fillForm();
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));

    expect(
      screen.getByRole("button", { name: "Создаём..." })
    ).toBeDisabled();

    resolveRegister(USER);
    expect(
      await screen.findByRole("heading", { name: "Проверьте email" })
    ).toBeInTheDocument();
  });

  it("повторная отправка письма: resendVerification и info-toast", async () => {
    const user = userEvent.setup();
    const register = vi.fn().mockResolvedValue(USER);
    const showToast = vi.fn();
    renderRegister({ user: null, loading: false, register }, showToast);

    fillForm({ email: " new@example.com " });
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    await screen.findByRole("heading", { name: "Проверьте email" });

    await user.click(
      screen.getByRole("button", { name: "Отправить письмо повторно" })
    );

    await waitFor(() =>
      expect(mResend).toHaveBeenCalledWith({ email: "new@example.com" })
    );
    expect(showToast).toHaveBeenCalledWith(
      "Если адрес зарегистрирован и не подтверждён, письмо отправлено.",
      "info"
    );
  });

  it("во время resend кнопка «Отправляем...» disabled", async () => {
    const user = userEvent.setup();
    let resolveResend: (value: { message: string }) => void = () => undefined;
    mResend.mockReturnValue(
      new Promise<{ message: string }>((resolve) => {
        resolveResend = resolve;
      })
    );
    const register = vi.fn().mockResolvedValue(USER);
    renderRegister({ user: null, loading: false, register });

    fillForm();
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    await screen.findByRole("heading", { name: "Проверьте email" });

    await user.click(
      screen.getByRole("button", { name: "Отправить письмо повторно" })
    );
    expect(
      screen.getByRole("button", { name: "Отправляем..." })
    ).toBeDisabled();

    resolveResend(RESEND_OK);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Отправить письмо повторно" })
      ).toBeEnabled()
    );
  });

  it("ошибка resend → error-toast", async () => {
    const user = userEvent.setup();
    mResend.mockRejectedValue(new Error("mail fail"));
    const register = vi.fn().mockResolvedValue(USER);
    const showToast = vi.fn();
    renderRegister({ user: null, loading: false, register }, showToast);

    fillForm();
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    await screen.findByRole("heading", { name: "Проверьте email" });

    await user.click(
      screen.getByRole("button", { name: "Отправить письмо повторно" })
    );

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("mail fail", "error")
    );
  });
});
