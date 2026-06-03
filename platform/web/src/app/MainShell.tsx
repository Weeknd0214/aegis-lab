import React from "react";
import { Switch, Route, Redirect } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { LabelingShell } from "@/modules/labeling/LabelingShell";
import { ModelsShell } from "@/modules/models/ModelsShell";
import { FleetShell } from "@/modules/fleet/FleetShell";
import { SystemShell } from "@/modules/system/SystemShell";
import { DashboardPage } from "@/modules/labeling/pages/DashboardPage";

export const MainShell: React.FC = () => {
  return (
    <div className="main-shell">
      <Sidebar />
      <div className="main-content">
        <div className="module-area">
          <Switch>
            {/* ── Dashboard (root) ── */}
            <Route exact path="/" component={DashboardPage} />
            {/* ── Module routes ── */}
            <Route path="/labeling" component={LabelingShell} />
            <Route path="/models" component={ModelsShell} />
            <Route path="/fleet" component={FleetShell} />
            <Route path="/system" component={SystemShell} />

            {/* ── Legacy redirects ── */}
            <Redirect from="/deliveries" to="/labeling/deliveries" />
            <Redirect from="/catalog" to="/labeling/catalog" />
            <Redirect from="/labeling/ml" to="/models/overview" />
            <Redirect from="/audit/:id" to="/system/audit/:id" />
            <Redirect from="/audit" to="/system/audit" />
            <Redirect from="/jobs" to="/system/jobs" />
            <Redirect from="/training" to="/models/training/records" />

            {/* ── 404 ── */}
            <Route>
              <div className="page-container text-center py-20">
                <h2 className="text-xl text-gray-400">页面未找到</h2>
                <p className="text-gray-400 text-sm mt-2">请检查 URL 是否正确</p>
              </div>
            </Route>
          </Switch>
        </div>
      </div>
    </div>
  );
};