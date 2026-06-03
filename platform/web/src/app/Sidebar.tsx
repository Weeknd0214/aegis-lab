import React, { useState, useEffect, useCallback } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { Userpic } from "@/components/ui/Userpic";

// ── Module definitions ──

interface NavItemDef {
  to: string;
  label: string;
  perm?: string;
  exact?: boolean;
}

interface ModuleDef {
  id: string;
  label: string;
  icon: string;
  requiredPerm: string;
  items: NavItemDef[];
}

const MODULES: ModuleDef[] = [
  {
    id: "labeling",
    label: "数据送标",
    icon: "📋",
    requiredPerm: "read:pending",
    items: [
      { to: "/labeling/workbench", label: "送标工作台", perm: "read:pending" },
      { to: "/labeling/campaigns", label: "标注进度", perm: "read:pending" },
      { to: "/labeling/review", label: "标注质检", perm: "read:pending" },
      { to: "/labeling/export", label: "导出与入库", perm: "read:pending" },
      { to: "/labeling/deliveries", label: "批次台账", perm: "read:deliveries" },
      { to: "/labeling/catalog", label: "数据目录", perm: "read:catalog" },
    ],
  },
  {
    id: "models",
    label: "模型管理",
    icon: "🧠",
    requiredPerm: "read:jobs",
    items: [
      { to: "/models/overview", label: "模型概览", perm: "read:jobs" },
      { to: "/models/datasets", label: "数据集版本", perm: "read:jobs" },
      { to: "/models/training/submit", label: "训练提交", perm: "write:approval_submit" },
      { to: "/models/training/records", label: "训练记录", perm: "read:jobs" },
      { to: "/models/evaluation", label: "评估管理", perm: "read:jobs" },
      { to: "/models/promotion", label: "模型晋级", perm: "write:approval_submit" },
    ],
  },
  {
    id: "fleet",
    label: "车队管理",
    icon: "🚛",
    requiredPerm: "read:fleet",
    items: [
      { to: "/fleet/dashboard", label: "车队总览", perm: "read:fleet" },
      { to: "/fleet/vehicles", label: "车辆管理", perm: "read:fleet" },
      { to: "/fleet/map", label: "实时地图", perm: "read:fleet" },
      { to: "/fleet/trips", label: "行程记录", perm: "read:fleet" },
      { to: "/fleet/tbox", label: "T-Box 配置", perm: "write:fleet" },
    ],
  },
  {
    id: "system",
    label: "系统管理",
    icon: "⚙️",
    requiredPerm: "",
    items: [
      { to: "/system/audit", label: "审核队列", perm: "read:audit" },
      { to: "/system/jobs", label: "任务监控", perm: "read:jobs" },
      { to: "/system/logs", label: "Agent 追踪", perm: "" },
      { to: "/system/audit-log", label: "操作日志", perm: "admin:users" },
      { to: "/system/users", label: "用户管理", perm: "admin:users" },
    ],
  },
];

// ── Health indicator ──

function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    let cancel = false;
    fetch("/api/v1/health", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => { if (!cancel) setOk(d?.status === "ok"); })
      .catch(() => { if (!cancel) setOk(false); });
    const t = setInterval(() => {
      fetch("/api/v1/health", { cache: "no-store" })
        .then((r) => r.json())
        .then((d) => { if (!cancel) setOk(d?.status === "ok"); })
        .catch(() => { if (!cancel) setOk(false); });
    }, 30000);
    return () => { cancel = true; clearInterval(t); };
  }, []);

  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${
        ok === null ? "bg-gray-300" : ok ? "bg-green-500" : "bg-red-500"
      }`}
      title={ok === null ? "检测中..." : ok ? "服务正常" : "服务异常"}
    />
  );
}

// ── Sidebar component ──

export const Sidebar: React.FC = () => {
  const { user, hasPermission, logout } = useAuth();
  const location = useLocation();

  // Determine which module is active from the current path
  const activeModuleId = MODULES.find(
    (m) => location.pathname.startsWith("/" + m.id)
  )?.id;

  // Accordion: only the active module is expanded
  const [expandedId, setExpandedId] = useState<string | null>(() => {
    // Restore from localStorage or use active module
    const saved = localStorage.getItem("sidebar:expanded");
    return saved || activeModuleId || null;
  });

  // Auto-expand active module when route changes
  useEffect(() => {
    if (activeModuleId) {
      setExpandedId(activeModuleId);
    }
  }, [activeModuleId]);

  const toggleModule = useCallback(
    (id: string) => {
      const next = expandedId === id ? null : id;
      setExpandedId(next);
      if (next) localStorage.setItem("sidebar:expanded", next);
      else localStorage.removeItem("sidebar:expanded");
    },
    [expandedId],
  );

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <NavLink to="/" className="no-underline text-inherit">
          HSAP <span className="text-gray-400 font-normal text-sm">数据闭环平台</span>
        </NavLink>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {MODULES.map((mod) => {
          const visibleItems = mod.items.filter(
            (item) => !item.perm || hasPermission(item.perm),
          );
          if (visibleItems.length === 0) return null;

          const isExpanded = expandedId === mod.id;
          const isActive = activeModuleId === mod.id;

          return (
            <div key={mod.id} className="module-group">
              <button
                className={`module-group-header ${isActive ? "active" : ""}`}
                onClick={() => toggleModule(mod.id)}
              >
                <span>{mod.icon}</span>
                <span>{mod.label}</span>
                <span className={`chevron ${isExpanded ? "open" : ""}`}>▶</span>
              </button>
              <div className={`module-group-items${isExpanded ? "" : " collapsed"}`}>
                  {visibleItems.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      exact={item.exact ?? false}
                      className="nav-item"
                      activeClassName="active"
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="flex items-center gap-2 mb-2">
          <Userpic username={user?.name || ""} size={28} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-800 truncate">
              {user?.name || "未登录"}
            </div>
            <div className="text-[11px] text-gray-400 truncate">
              {user?.roles?.map((r: {code: string; name: string}) => r.name).join("、") || ""}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between text-gray-400">
          <div className="flex items-center gap-1">
            <HealthDot />
            <span className="text-[11px]">API</span>
          </div>
          <button
            onClick={logout}
            className="text-[11px] text-gray-400 hover:text-red-500 transition-colors"
          >
            退出
          </button>
        </div>
      </div>
    </aside>
  );
};
