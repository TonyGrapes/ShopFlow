// frontend/src/context/AuthProvider.tsx
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
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
import { AuthContext } from "./authContext";
import type { AuthContextValue } from "./authContext";
import { useToast } from "../hooks/useToast";
import type {
  LoginRequest,
  RegisterRequest,
  UserResponse,
} from "../types/auth";

interface Props {
  children: ReactNode;
}

export function AuthProvider({ children }: Props) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { showToast } = useToast();

  // Bootstrap: пробуем восстановить сессию по httpOnly refresh-cookie.
  // StrictMode запускает эффект дважды; refreshAccessToken защищён
  // single-flight-промисом, поэтому ротация cookie не дублируется.
  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const refreshed = await refreshAccessToken();
        if (cancelled) return;

        if (refreshed !== null) {
          const me = await fetchMe();
          if (!cancelled) {
            setUser(me);
          }
        }
      } catch {
        if (!cancelled) {
          setUser(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  // 401 после неудачного refresh — окончательная потеря сессии.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);

      const path = window.location.pathname + window.location.search;
      if (
        path !== "/login" &&
        path !== "/register" &&
        path !== "/verify-email"
      ) {
        showToast("Сессия истекла. Войдите снова.", "error");
        navigate("/login", { state: { from: path } });
      }
    });

    return () => {
      setUnauthorizedHandler(null);
    };
  }, [navigate, showToast]);

  const login = useCallback(async (data: LoginRequest) => {
    const tokens = await loginUser(data);
    setAccessToken(tokens.access_token);

    try {
      const me = await fetchMe();
      setUser(me);
    } catch (err) {
      setAccessToken(null);
      setUser(null);
      throw err;
    }
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    return registerUser(data);
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      // Даже если сервер недоступен, локальную сессию очищаем.
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await fetchMe();
    setUser(me);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: user !== null,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, loading, login, register, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
