import React from "react";
import { Switch, Route, Redirect, NavLink, useRouteMatch, useLocation } from "react-router-dom";
import { ModuleGuard } from "@/components/ModuleGuard";
import { useAuth } from "@/app/AuthContext";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { MyTasksPage } from "./pages/MyTasksPage";
import { CampaignsPage } from "./pages/CampaignsPage";
import { ExportPage } from "./pages/ExportPage";
import { DeliveriesPage } from "./pages/DeliveriesPage";
import { CatalogPage } from "./pages/CatalogPage";
import { QualityReviewPage } from "./pages/QualityReviewPage";
import { SimulationStudioPage } from "./pages/SimulationStudioPage";
import { AnnotationPage } from "./pages/AnnotationPage";

const TABS = [
  { to: "/labeling/my-tasks", label: "我的标注", perm: "read:pending" },
  { to: "/labeling/workbench", label: "送标工作台", perm: "read:pending", coordinatorOnly: true },
  { to: "/labeling/campaigns", label: "标注进度", perm: "read:pending", coordinatorOnly: true },
  { to: "/labeling/review", label: "标注质检", perm: "write:approval_review" },
  { to: "/labeling/export", label: "导出与入库", perm: "read:pending", coordinatorOnly: true },
  { to: "/labeling/deliveries", label: "批次台账", perm: "read:deliveries" },
  { to: "/labeling/catalog", label: "数据目录", perm: "read:catalog" },
  { to: "/labeling/simulate", label: "仿真工坊", perm: "read:pending", coordinatorOnly: true },
];

export const LabelingShell: React.FC = () => {
  const { path } = useRouteMatch();
  const location = useLocation();
  const { hasPermission } = useAuth();
  const isCoordinator = hasPermission("write:labeling_assign");
  const isAnnotate = /\/labeling\/annotate\//.test(location.pathname);

  const visibleTabs = TABS.filter((tab) => {
    if (tab.coordinatorOnly && !isCoordinator) return false;
    if (tab.perm && !hasPermission(tab.perm)) return false;
    return true;
  });

  const defaultPath = isCoordinator ? "/labeling/workbench" : "/labeling/my-tasks";

  return (
    <ModuleGuard requiredPerms={["read:pending", "read:deliveries", "read:catalog", "write:delivery_submit"]}>
      <div className={isAnnotate ? "h-[calc(100vh-0px)] flex flex-col min-h-0" : undefined}>
        {!isAnnotate && (
          <nav className="module-tabs">
            {visibleTabs.map((tab) => (
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
        )}
        <Switch>
          <Route exact path={`${path}`} render={() => <Redirect to={defaultPath} />} />
          <Route path={`${path}/annotate/:campaignId`} component={AnnotationPage} />
          <Route path={`${path}/my-tasks`} component={MyTasksPage} />
          <Route path={`${path}/workbench`} component={WorkbenchPage} />
          <Route path={`${path}/review/:campaignId`} component={QualityReviewPage} />
          <Route path={`${path}/review`} component={QualityReviewPage} />
          <Route path={`${path}/campaigns`} component={CampaignsPage} />
          <Route path={`${path}/export`} component={ExportPage} />
          <Route path={`${path}/deliveries`} component={DeliveriesPage} />
          <Route path={`${path}/catalog`} component={CatalogPage} />
          <Route path={`${path}/simulate`} component={SimulationStudioPage} />
        </Switch>
      </div>
    </ModuleGuard>
  );
};
