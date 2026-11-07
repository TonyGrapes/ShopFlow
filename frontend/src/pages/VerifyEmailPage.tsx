// frontend/src/pages/VerifyEmailPage.tsx
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { verifyEmailOnce } from "../api/auth";
import { getErrorMessage } from "../utils/errors";

type Status = "idle" | "loading" | "success" | "error";

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const tokenFromQuery = searchParams.get("token") ?? "";

  const [tokenInput, setTokenInput] = useState(tokenFromQuery);
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (tokenFromQuery.length === 0) {
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setMessage(null);

    verifyEmailOnce(tokenFromQuery)
      .then((response) => {
        if (!cancelled) {
          setStatus("success");
          setMessage(response.message);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setStatus("error");
          setMessage(getErrorMessage(err));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [tokenFromQuery]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = tokenInput.trim();
    if (token.length === 0) {
      setStatus("error");
      setMessage("Вставьте токен из письма");
      return;
    }

    setStatus("loading");
    setMessage(null);
    try {
      const response = await verifyEmailOnce(token);
      setStatus("success");
      setMessage(response.message);
    } catch (err) {
      setStatus("error");
      setMessage(getErrorMessage(err));
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Подтверждение email</h1>

        {status === "loading" && (
          <p>Проверяем токен подтверждения...</p>
        )}

        {status === "success" && (
          <div className="form__hint form__hint--success">
            <p>Email подтверждён. Теперь можно войти.</p>
            <Link to="/login" className="btn btn--primary">
              Перейти ко входу
            </Link>
          </div>
        )}

        {status === "error" && message !== null && (
          <p className="form__error">{message}</p>
        )}

        {(status === "idle" || status === "error") && (
          <form className="form" onSubmit={handleSubmit}>
            <label className="form__field">
              <span>Токен из письма</span>
              <input
                type="text"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Вставьте токен подтверждения"
                required
              />
            </label>

            <div className="form__actions">
              <button type="submit" className="btn btn--primary">
                Подтвердить email
              </button>
              <Link to="/login" className="btn btn--secondary">
                Ко входу
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
