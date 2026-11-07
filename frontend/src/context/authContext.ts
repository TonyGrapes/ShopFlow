// frontend/src/context/authContext.ts
import { createContext } from "react";
import type {
  LoginRequest,
  RegisterRequest,
  UserResponse,
} from "../types/auth";

export interface AuthContextValue {
  user: UserResponse | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<UserResponse>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
