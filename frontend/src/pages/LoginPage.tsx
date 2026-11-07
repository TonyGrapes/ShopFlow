// frontend/src/pages/LoginPage.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { resendVerification } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import { isValidEmail } from "../utils/validation";

function getRedirectPath(state: unknown): string {
  if (typeof state === "object" && state !== null && "from" in state) {
    const from = (state as { from?: unknown }).from;
    if (typeof from === "string") {
      return from;
    }
  }
  return "/";
}

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = getRedirectPath(location.state);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [needVerification, setNeedVerification] = useState(false);

  if (!loading && user !== null) {
    return <Navigate to={redirectTo} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setNeedVerification(false);

    if (!isValidEmail(email)) {
      setFormError("Введите корректный email");
      return;
    }
    if (password.length === 0) {
      setFormError("Введите пароль");
      return;
    }

    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setNeedVerification(true);
        setFormError(err.detail);
      } else {
        setFormError(getErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    if (!isValidEmail(email)) {
      setFormError("Введите корректный email");
      return;
    }

    setResending(true);
    try {
      await resendVerification({ email: email.trim() });
      showToast(
        "Если адрес зарегистрирован и не подтверждён, письмо отправлено.",
        "info"
      );
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Вход</h1>

        <form className="form" onSubmit={handleSubmit}>
          <label className="form__field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              maxLength={255}
              required
            />
          </label>

          <label className="form__field">
            <span>Пароль</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              maxLength={128}
              required
            />
          </label>

          {formError !== null && <p className="form__error">{formError}</p>}

          {needVerification && (
            <div className="form__hint">
              <p>
                Email не подтверждён. В dev-режиме ссылка печатается
                в логах backend.
              </p>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={handleResend}
                disabled={resending}
              >
                {resending ? "Отправляем..." : "Отправить письмо повторно"}
              </button>
            </div>
          )}

          <div className="form__actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={submitting}
            >
              {submitting ? "Входим..." : "Войти"}
            </button>
          </div>
        </form>

        <p className="auth-card__footer">
          Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
        </p>
      </div>
    </div>
  );
}
