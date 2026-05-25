import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type AuthUser } from "../api/client";

const TOKEN_KEY = "as_access_token";

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  token: string | null;
  authConfig: { feishu_enabled: boolean; dev_auth_enabled: boolean } | null;
  loginFeishu: () => void;
  loginDev: (name?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  hasPermission: (code: string) => boolean;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [authConfig, setAuthConfig] = useState<{ feishu_enabled: boolean; dev_auth_enabled: boolean } | null>(null);

  useEffect(() => {
    // 支持后端回调重定向到 /?token=...
    const url = new URL(window.location.href);
    const tokenFromQuery = url.searchParams.get("token");
    if (tokenFromQuery) {
      localStorage.setItem(TOKEN_KEY, tokenFromQuery);
      api.setToken(tokenFromQuery);
      url.searchParams.delete("token");
      window.history.replaceState({}, "", url.toString());
      setToken(tokenFromQuery);
    }
  }, []);

  const applyToken = useCallback((t: string | null) => {
    setToken(t);
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
    api.setToken(t);
  }, []);

  const refreshUser = useCallback(async () => {
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      applyToken(null);
      setUser(null);
    }
  }, [token, applyToken]);

  useEffect(() => {
    api.authConfig().then(setAuthConfig).catch(() => setAuthConfig({ feishu_enabled: false, dev_auth_enabled: true }));
  }, []);

  useEffect(() => {
    api.setToken(token);
    if (token) {
      refreshUser().finally(() => setLoading(false));
    } else {
      setUser(null);
      setLoading(false);
    }
  }, [token, refreshUser]);

  const loginFeishu = () => {
    window.location.href = "/api/v1/auth/feishu/authorize";
  };

  const loginDev = async (name?: string) => {
    const res = await api.devLogin(name);
    applyToken(res.access_token);
    setUser(res.user);
  };

  const logout = () => {
    applyToken(null);
    setUser(null);
  };

  const hasPermission = useCallback(
    (code: string) => {
      if (!user) return false;
      const perms = user.permissions || [];
      return perms.includes("*") || perms.includes(code);
    },
    [user]
  );

  const value = useMemo(
    () => ({
      user,
      loading,
      token,
      loginFeishu,
      loginDev,
      logout,
      refreshUser,
      hasPermission,
      authConfig,
    }),
    [user, loading, token, refreshUser, hasPermission, authConfig]
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
