import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { PageQueryState } from "@/components/PageQueryState";
import { Badge } from "@/components/ui/Badge";

export const DashboardPage: React.FC = () => {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    hsapApi.fleetSummary()
      .then(setSummary)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>车队总览</h1>
        <p>车队实时状态概览</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <div className="text-3xl font-bold text-blue-700">{String(summary?.active_vehicles ?? "—")}</div>
            <div className="text-sm text-gray-500 mt-1">活跃车辆</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-green-600">{String(summary?.active_runs ?? "—")}</div>
            <div className="text-sm text-gray-500 mt-1">进行中行程</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-orange-600">{String(summary?.total_vehicles ?? "—")}</div>
            <div className="text-sm text-gray-500 mt-1">总车辆数</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-gray-600">{String(summary?.total_runs ?? "—")}</div>
            <div className="text-sm text-gray-500 mt-1">总行程数</div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">快捷操作</div>
          <div className="flex gap-2">
            <Link to="/fleet/map" className="text-blue-600 text-sm hover:underline">查看实时地图 →</Link>
            <Link to="/fleet/vehicles" className="text-blue-600 text-sm hover:underline">管理车辆 →</Link>
            <Link to="/fleet/trips" className="text-blue-600 text-sm hover:underline">行程记录 →</Link>
          </div>
        </div>
      </PageQueryState>
    </div>
  );
};
