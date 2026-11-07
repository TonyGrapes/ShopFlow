// frontend/src/pages/RegisterPage.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { resendVerification } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import {
  isValidEmail,
  isValidPassword,
  isValidPhone,
} from "../utils/validation";

export function RegisterPage() {
  const { user, loading, register } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  if (!loading && user !== null) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (!isValidEmail(email)) {
      setFormError("Введите корректный email");
      return;
    }
    if (!isValidPassword(password)) {
      setFormError("Пароль должен быть от 8 до 128 символов");
      return;
    }
    if (firstName.trim().length === 0 || firstName.trim().length > 100) {
      setFormError("Имя должно быть от 1 до 100 символов");
      return;
    }
    if (lastName.trim().length === 0 || lastName.trim().length > 100) {
      setFormError("Фамилия должна быть от 1 до 100 символов");
      return;
    }
    if (!isValidPhone(phoneNumber)) {
      setFormError("Введите телефон в формате +7 999 000-00-00");
      return;
    }

    setSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneNumber.trim(),
      });
      setRegistered(true);
      showToast("Аккаунт создан. Подтвердите email.", "success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setFormError("Этот email уже зарегистрирован");
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

  if (registered) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Проверьте email</h1>
          <p>
            Аккаунт создан, но вход станет доступен только после
            подтверждения email.
          </p>
          <p className="form__hint">
            В dev-режиме ссылка с токеном печатается в логах backend.
            Откройте <Link to="/verify-email">страницу подтверждения</Link>{" "}
            и вставьте токен вручную.
          </p>

          <div className="form__actions">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleResend}
              disabled={resending}
            >
              {resending ? "Отправляем..." : "Отправить письмо повторно"}
            </button>
            <Link to="/login" className="btn btn--primary">
              Перейти ко входу
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Регистрация</h1>

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
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              required
            />
          </label>

          <label className="form__field">
            <span>Имя</span>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              autoComplete="given-name"
              maxLength={100}
              required
            />
          </label>

          <label className="form__field">
            <span>Фамилия</span>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              autoComplete="family-name"
              maxLength={100}
              required
            />
          </label>

          <label className="form__field">
            <span>Телефон</span>
            <input
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              autoComplete="tel"
              placeholder="+7 999 000-00-00"
              maxLength={20}
              required
            />
          </label>

          {formError !== null && <p className="form__error">{formError}</p>}

          <div className="form__actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={submitting}
            >
              {submitting ? "Создаём..." : "Создать аккаунт"}
            </button>
          </div>
        </form>

        <p className="auth-card__footer">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </div>
    </div>
  );
}
