import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import type { ReactNode } from "react";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="empty-state">登录验证中…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function RequirePermission({ code, children }: { code: string; children: ReactNode }) {
  const { hasPermission } = useAuth();
  if (!hasPermission(code)) {
    return <p className="empty-state">无权访问此页面（需要 {code}）</p>;
  }
  return <>{children}</>;
}
