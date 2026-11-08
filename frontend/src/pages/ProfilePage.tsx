// frontend/src/pages/ProfilePage.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { changePassword, updateProfile } from "../api/auth";
import { LoadingState } from "../components/LoadingState";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import { isValidPassword, isValidPhone } from "../utils/validation";

export function ProfilePage() {
  const { user, loading, refreshUser, logout } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();

  // Profile form
  const [firstName, setFirstName] = useState(user?.first_name ?? "");
  const [lastName, setLastName] = useState(user?.last_name ?? "");
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number ?? "");
  const [profileSubmitting, setProfileSubmitting] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Password form
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  if (loading) return <LoadingState />;
  if (user === null) return null;

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileError(null);

    const trimmedFirst = firstName.trim();
    const trimmedLast = lastName.trim();
    const trimmedPhone = phoneNumber.trim();

    if (trimmedFirst.length === 0 || trimmedFirst.length > 100) {
      setProfileError("Имя должно быть от 1 до 100 символов");
      return;
    }
    if (trimmedLast.length === 0 || trimmedLast.length > 100) {
      setProfileError("Фамилия должна быть от 1 до 100 символов");
      return;
    }
    if (!isValidPhone(trimmedPhone)) {
      setProfileError("Введите телефон в формате +7 999 000-00-00");
      return;
    }

    setProfileSubmitting(true);
    try {
      await updateProfile({
        first_name: trimmedFirst,
        last_name: trimmedLast,
        phone_number: trimmedPhone,
      });
      await refreshUser();
      showToast("Профиль сохранён", "success");
    } catch (err) {
      setProfileError(getErrorMessage(err));
    } finally {
      setProfileSubmitting(false);
    }
  }

  async function handlePasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null);

    if (oldPassword.length === 0) {
      setPasswordError("Введите текущий пароль");
      return;
    }
    if (!isValidPassword(newPassword)) {
      setPasswordError("Новый пароль должен быть от 8 до 128 символов");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("Пароли не совпадают");
      return;
    }

    setPasswordSubmitting(true);
    try {
      await changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      });
      showToast("Пароль изменён. Войдите снова.", "success");
      await logout();
      navigate("/login", { replace: true });
    } catch (err) {
      setPasswordError(getErrorMessage(err));
    } finally {
      setPasswordSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Профиль</h1>

        {/* ========== Форма профиля ========== */}
        <form className="form" onSubmit={handleProfileSubmit}>
          <h2>Личные данные</h2>

          <label className="form__field">
            <span>Email (не редактируется)</span>
            <input type="email" value={user.email} disabled readOnly />
          </label>

          <label className="form__field">
            <span>Имя</span>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
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
              maxLength={20}
              required
            />
          </label>

          {profileError !== null && (
            <p className="form__error">{profileError}</p>
          )}

          <div className="form__actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={profileSubmitting}
            >
              {profileSubmitting ? "Сохраняем..." : "Сохранить"}
            </button>
          </div>
        </form>

        {/* ========== Форма смены пароля ========== */}
        <form
          className="form"
          onSubmit={handlePasswordSubmit}
          style={{ marginTop: "2rem" }}
        >
          <h2>Смена пароля</h2>

          <label className="form__field">
            <span>Текущий пароль</span>
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              autoComplete="current-password"
              maxLength={128}
              required
            />
          </label>

          <label className="form__field">
            <span>Новый пароль</span>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              required
            />
          </label>

          <label className="form__field">
            <span>Подтверждение пароля</span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              required
            />
          </label>

          {passwordError !== null && (
            <p className="form__error">{passwordError}</p>
          )}

          <div className="form__actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={passwordSubmitting}
            >
              {passwordSubmitting ? "Меняем..." : "Сменить пароль"}
            </button>
          </div>
        </form>

        <p className="auth-card__footer">
          <Link to="/">← В каталог</Link>
        </p>
      </div>
    </div>
  );
}