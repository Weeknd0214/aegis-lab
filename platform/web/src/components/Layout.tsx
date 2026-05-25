import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/labeling", icon: "◎", label: "送标工作台", badge: "pending" as const, perm: "read:pending" },
  { to: "/catalog", icon: "▤", label: "数据目录", perm: "read:catalog" },
  { to: "/audit", icon: "✓", label: "审核管理", badge: "audit" as const, perm: "read:audit" },
  { to: "/jobs", icon: "◷", label: "任务监控", perm: "read:jobs" },
  { to: "/training", icon: "▶", label: "模型训练", perm: "write:approval_submit" },
  { to: "/logs", icon: "☰", label: "审计日志", perm: "read:audit" },
];

export function Layout() {
  const { user, logout, hasPermission } = useAuth();
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [pendingN, setPendingN] = useState(0);
  const [auditN, setAuditN] = useState(0);

  const refreshMeta = async () => {
    try {
      await api.health();
      setApiOk(true);
      if (hasPermission("read:pending")) {
        const pending = await api.pending();
        const actionable = (pending.batches || []).filter((b) =>
          ["returned", "raw_pool", "out_for_labeling"].includes(b.stage)
        );
        setPendingN(actionable.length);
      }
      if (hasPermission("read:audit")) {
        const aud = await api.listApprovals("pending");
        setAuditN(aud.items?.length || 0);
      }
    } catch {
      setApiOk(false);
    }
  };

  useEffect(() => {
    refreshMeta();
    const t = setInterval(refreshMeta, 30000);
    return () => clearInterval(t);
  }, [user]);

  const path = location.pathname.replace(/^\//, "").split("/")[0] || "labeling";
  const title = NAV.find((n) => n.to.slice(1) === path)?.label || "送标工作台";
  const roleLabel = user?.roles?.map((r) => r.name).join(" · ") || "";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo" aria-hidden="true">
            <svg viewBox="0 0 40 40" fill="none">
              <rect width="40" height="40" rx="10" fill="url(#g)" />
              <path d="M12 28V12h6l4 10 4-10h6v16h-5V18l-4 10h-4l-4-10v10H12z" fill="white" fillOpacity="0.95" />
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="40" y2="40">
                  <stop stopColor="#0ea5e9" />
                  <stop offset="1" stopColor="#06b6d4" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-company">Huaxu Sentinel</span>
            <span className="brand-product">HSAP · 主动安全算法平台</span>
          </div>
        </div>
        <nav className="nav">
          {NAV.filter((n) => hasPermission(n.perm)).map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}>
              <span className="nav-icon">{n.icon}</span> {n.label}
              {n.badge === "pending" && pendingN > 0 && <span className="nav-badge">{pendingN}</span>}
              {n.badge === "audit" && auditN > 0 && <span className="nav-badge">{auditN}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-chip">
            {user?.avatar_url ? <img src={user.avatar_url} alt="" className="user-avatar" /> : <span className="user-avatar user-avatar-ph">{user?.name?.[0]}</span>}
            <div>
              <div className="user-name">{user?.name}</div>
              <div className="user-role text-dim">{roleLabel}</div>
            </div>
          </div>
          <div className="env-chip">
            <span className="env-dot" style={{ background: apiOk ? "var(--success)" : apiOk === false ? "var(--warning)" : undefined }} />
            <span>{apiOk ? "算法服务运行中" : apiOk === false ? "算法服务离线" : "服务检测中…"}</span>
          </div>
          <button type="button" className="btn btn-sm btn-ghost btn-logout" onClick={logout}>退出登录</button>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <div className="topbar-title">
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <button type="button" className="btn btn-ghost" onClick={() => refreshMeta()}>刷新</button>
          </div>
        </header>
        <main className="content">
          <Outlet context={{ refreshMeta }} />
        </main>
      </div>
    </div>
  );
}
