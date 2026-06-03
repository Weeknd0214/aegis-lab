import { useAuth } from "@/app/AuthContext";
import { Redirect } from "react-router-dom";
import type { ReactNode } from "react";

interface ModuleGuardProps {
  requiredPerms: string[];
  fallback?: "redirect" | "message";
  children: ReactNode;
}

export const ModuleGuard = ({ requiredPerms, fallback = "redirect", children }: ModuleGuardProps) => {
  const { hasPermission } = useAuth();
  const hasAccess = requiredPerms.some((p) => hasPermission(p));
  if (!hasAccess) {
    if (fallback === "redirect") return <Redirect to="/" />;
    return (
      <div className="page-container">
        <div className="card text-center py-12">
          <p className="text-gray-500 text-lg">您没有访问此模块的权限</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
};
