import React from "react";
import { Switch, Route, Redirect, NavLink, useRouteMatch } from "react-router-dom";
import { ModuleGuard } from "@/components/ModuleGuard";
import { AuditQueuePage } from "./pages/AuditQueuePage";
import { AuditDetailPage } from "./pages/AuditDetailPage";
import { JobMonitorPage } from "./pages/JobMonitorPage";
import { ExecutionLogsPage } from "./pages/ExecutionLogsPage";
import { UserManagementPage } from "./pages/UserManagementPage";
import { AuditLogPage } from "./pages/AuditLogPage";

const TABS = [
  { to: "/system/audit", label: "审核队列", perm: "read:audit" },
  { to: "/system/jobs", label: "任务监控", perm: "read:jobs" },
  { to: "/system/audit-log", label: "操作日志", perm: "admin:users" },
  { to: "/system/logs", label: "Agent 追踪", perm: "" },
  { to: "/system/users", label: "用户管理", perm: "admin:users" },
];

export const SystemShell: React.FC = () => {
  const { path } = useRouteMatch();

  return (
    <ModuleGuard requiredPerms={["read:audit", "read:jobs", "admin:users", ""]}>
      <div>
        <nav className="module-tabs">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className="module-tab"
              activeClassName="active"
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <Switch>
          <Route exact path={`${path}`} render={() => <Redirect to="/system/audit" />} />
          <Route exact path={`${path}/audit`} component={AuditQueuePage} />
          <Route path={`${path}/audit/:id`} component={AuditDetailPage} />
          <Route path={`${path}/jobs`} component={JobMonitorPage} />
          <Route path={`${path}/audit-log`} component={AuditLogPage} />
          <Route path={`${path}/logs`} component={ExecutionLogsPage} />
          <Route path={`${path}/users`} component={UserManagementPage} />
        </Switch>
      </div>
    </ModuleGuard>
  );
};
