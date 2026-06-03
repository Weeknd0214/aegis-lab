import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { hsapApi, hasPermission, type AuthUser } from "./hsap-api";

type AuthCtx = {
  user: AuthUser | null;
  loading: boolean;
  authConfig: { feishu_enabled: boolean; dev_auth_enabled: boolean } | null;
  loginDev: (name?: string) => Promise<void>;
  loginFeishu: () => void;
  logout: () => void;
  hasPermission: (perm: string) => boolean;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [authConfig, setAuthConfig] = useState<AuthCtx["authConfig"]>(null);

  const bootstrap = useCallback(async () => {
    const params = new URLSearchParams(window.location.search);
    const tokenFromUrl = params.get("token");
    if (tokenFromUrl) {
      hsapApi.setToken(tokenFromUrl);
      window.history.replaceState({}, "", window.location.pathname);
    }
    try {
      setAuthConfig(await hsapApi.authConfig());
      if (hsapApi.getToken()) {
        setUser(await hsapApi.me());
      }
    } catch {
      hsapApi.setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  const loginDev = useCallback(async (name?: string) => {
    const res = await hsapApi.devLogin(name);
    hsapApi.setToken(res.access_token);
    setUser(res.user);
  }, []);

  const loginFeishu = useCallback(() => {
    window.location.assign(`${window.location.origin}/api/v1/auth/feishu/authorize`);
  }, []);

  const logout = useCallback(() => {
    hsapApi.setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, authConfig, loginDev, loginFeishu, logout, hasPermission: (perm: string) => hasPermission(user, perm) }),
    [user, loading, authConfig, loginDev, loginFeishu, logout],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
