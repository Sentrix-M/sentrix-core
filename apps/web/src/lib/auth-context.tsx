"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  authApi,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  type LoginInput,
  type RegisterInput,
  type TokenPair,
  type User,
} from "@/lib/api";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  user: User | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<User | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKENS_KEY = "sentrix.tokens";

function persistTokens(pair: TokenPair) {
  setTokens(pair.access_token, pair.refresh_token);
  try {
    window.localStorage.setItem(TOKENS_KEY, JSON.stringify(pair));
  } catch {
    // Storage unavailable (private mode); tokens stay in-memory only.
  }
}

function readPersistedTokens(): TokenPair | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(TOKENS_KEY);
    return raw ? (JSON.parse(raw) as TokenPair) : null;
  } catch {
    return null;
  }
}

function clearPersistedTokens() {
  clearTokens();
  try {
    window.localStorage.removeItem(TOKENS_KEY);
  } catch {
    // ignore
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const restoreSession = useCallback(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
    const persisted = readPersistedTokens();
    if (!persisted) {
      setStatus("unauthenticated");
      return;
    }
    setTokens(persisted.access_token, persisted.refresh_token);

    try {
      const me = await authApi.me();
      setUser(me);
      setStatus("authenticated");
    } catch {
      clearPersistedTokens();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  const login = useCallback(async (input: LoginInput) => {
    const pair = await authApi.login(input);
    persistTokens(pair);
    const me = await authApi.me();
    setUser(me);
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const pair = await authApi.register(input);
    persistTokens(pair);
    const me = await authApi.me();
    setUser(me);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    const refresh = getRefreshToken();
    const access = getAccessToken();
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        // Even if the server call fails, the local session must be cleared.
      }
    }
    void access;
    clearPersistedTokens();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
      setStatus("authenticated");
      return me;
    } catch (error) {
      clearPersistedTokens();
      setUser(null);
      setStatus("unauthenticated");
      return null;
    }
  }, []);

  // Expose `api` refresh failure → clear session via `refreshUser`.
  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      isAuthenticated: status === "authenticated",
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, status, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return ctx;
}

export { getAccessToken, getRefreshToken };

