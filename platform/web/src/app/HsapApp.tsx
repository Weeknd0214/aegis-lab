import React from "react";
import { BrowserRouter, Switch, Route, Redirect } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import { MainShell } from "./MainShell";
import { LoginPage } from "@/pages/LoginPage";

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400 animate-pulse">加载中...</div>
      </div>
    );
  }
  if (!user) return <Redirect to="/login" />;
  return <>{children}</>;
};

const AppRoutes: React.FC = () => (
  <Switch>
    <Route exact path="/login" component={LoginPage} />
    {/* All other routes — inside MainShell */}
    <Route>
      <RequireAuth>
        <MainShell />
      </RequireAuth>
    </Route>
  </Switch>
);

export const HsapApp: React.FC = () => (
  <BrowserRouter>
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  </BrowserRouter>
);
