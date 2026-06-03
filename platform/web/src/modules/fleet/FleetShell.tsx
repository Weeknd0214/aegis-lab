import React from "react";
import { Switch, Route, Redirect, NavLink, useRouteMatch } from "react-router-dom";
import { ModuleGuard } from "@/components/ModuleGuard";
import { DashboardPage } from "./pages/DashboardPage";
import { VehiclesPage } from "./pages/VehiclesPage";
import { LiveMapPage } from "./pages/LiveMapPage";
import { TripRecordsPage } from "./pages/TripRecordsPage";
import { TboxConfigPage } from "./pages/TboxConfigPage";

const TABS = [
  { to: "/fleet/dashboard", label: "车队总览", perm: "read:fleet" },
  { to: "/fleet/vehicles", label: "车辆管理", perm: "read:fleet" },
  { to: "/fleet/map", label: "实时地图", perm: "read:fleet" },
  { to: "/fleet/trips", label: "行程记录", perm: "read:fleet" },
  { to: "/fleet/tbox", label: "T-Box 配置", perm: "write:fleet" },
];

export const FleetShell: React.FC = () => {
  const { path } = useRouteMatch();

  return (
    <ModuleGuard requiredPerms={["read:fleet"]}>
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
          <Route exact path={`${path}`} render={() => <Redirect to="/fleet/dashboard" />} />
          <Route path={`${path}/dashboard`} component={DashboardPage} />
          <Route path={`${path}/vehicles`} component={VehiclesPage} />
          <Route path={`${path}/map`} component={LiveMapPage} />
          <Route path={`${path}/trips`} component={TripRecordsPage} />
          <Route path={`${path}/tbox`} component={TboxConfigPage} />
        </Switch>
      </div>
    </ModuleGuard>
  );
};
