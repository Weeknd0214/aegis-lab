import React from "react";
import { Switch, Route, Redirect, NavLink, useRouteMatch } from "react-router-dom";
import { ModuleGuard } from "@/components/ModuleGuard";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { CampaignsPage } from "./pages/CampaignsPage";
import { ExportPage } from "./pages/ExportPage";
import { DeliveriesPage } from "./pages/DeliveriesPage";
import { CatalogPage } from "./pages/CatalogPage";
import { QualityReviewPage } from "./pages/QualityReviewPage";
import { SimulationStudioPage } from "./pages/SimulationStudioPage";

const TABS = [
  { to: "/labeling/workbench", label: "送标工作台", perm: "read:pending" },
  { to: "/labeling/campaigns", label: "标注进度", perm: "read:pending" },
  { to: "/labeling/review", label: "标注质检", perm: "write:approval_review" },
  { to: "/labeling/export", label: "导出与入库", perm: "read:pending" },
  { to: "/labeling/deliveries", label: "批次台账", perm: "read:deliveries" },
  { to: "/labeling/catalog", label: "数据目录", perm: "read:catalog" },
  { to: "/labeling/simulate", label: "仿真工坊", perm: "read:pending" },
];

export const LabelingShell: React.FC = () => {
  const { path } = useRouteMatch();

  return (
    <ModuleGuard requiredPerms={["read:pending", "read:deliveries", "read:catalog", "write:delivery_submit"]}>
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
          <Route exact path={`${path}`} render={() => <Redirect to="/labeling/workbench" />} />
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
