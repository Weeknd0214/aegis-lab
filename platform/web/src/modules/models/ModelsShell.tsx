import React from "react";
import { Switch, Route, Redirect, NavLink, useRouteMatch } from "react-router-dom";
import { ModuleGuard } from "@/components/ModuleGuard";
import { OverviewPage } from "./pages/OverviewPage";
import { TrainingSubmitPage } from "./pages/TrainingSubmitPage";
import { TrainingRecordsPage } from "./pages/TrainingRecordsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { PromotionPage } from "./pages/PromotionPage";
import { DatasetVersionsPage } from "./pages/DatasetVersionsPage";

const TABS = [
  { to: "/models/overview", label: "模型概览", perm: "read:jobs" },
  { to: "/models/datasets", label: "数据集版本", perm: "read:jobs" },
  { to: "/models/training/submit", label: "训练提交", perm: "write:approval_submit" },
  { to: "/models/training/records", label: "训练记录", perm: "read:jobs" },
  { to: "/models/evaluation", label: "评估管理", perm: "read:jobs" },
  { to: "/models/promotion", label: "模型晋级", perm: "write:approval_submit" },
];

export const ModelsShell: React.FC = () => {
  const { path } = useRouteMatch();

  return (
    <ModuleGuard requiredPerms={["read:jobs", "write:approval_submit"]}>
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
          <Route exact path={`${path}`} render={() => <Redirect to="/models/overview" />} />
          <Route path={`${path}/overview`} component={OverviewPage} />
          <Route path={`${path}/datasets`} component={DatasetVersionsPage} />
          <Route path={`${path}/training/submit`} component={TrainingSubmitPage} />
          <Route path={`${path}/training/records`} component={TrainingRecordsPage} />
          <Route path={`${path}/evaluation`} component={EvaluationPage} />
          <Route path={`${path}/promotion`} component={PromotionPage} />
        </Switch>
      </div>
    </ModuleGuard>
  );
};
