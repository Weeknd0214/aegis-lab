import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { Button } from "@/components/ui/Button";

type ModelEntry = { name?: string; version?: string; task?: string; project?: string; metrics?: Record<string, number>; status?: string; created_at?: string };

export const OverviewPage: React.FC = () => {
  const [registry, setRegistry] = useState<Record<string, unknown> | null>(null);
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      hsapApi.getModelRegistry("dms"),
      hsapApi.listTrainingRecords({ limit: 5 }),
    ])
      .then(([reg, rec]) => { setRegistry(reg); setRecords((rec.items || []) as Record<string, unknown>[]); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const models = (registry?.models || []) as ModelEntry[];
  const activePacks = (registry?.active_packs || []) as string[];
  const completedCount = records.filter((r) => r.status === "completed").length;
  const runningCount = records.filter((r) => r.status === "running").length;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>模型概览</h1>
        <p>模型注册表与最近训练动态</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        {/* KPI cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <div className="text-3xl font-bold text-blue-700">{models.length || "—"}</div>
            <div className="text-sm text-gray-500 mt-1">已注册模型</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-green-600">{completedCount}</div>
            <div className="text-sm text-gray-500 mt-1">已完成训练</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-orange-600">{runningCount}</div>
            <div className="text-sm text-gray-500 mt-1">执行中</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-gray-600">{activePacks.length || "—"}</div>
            <div className="text-sm text-gray-500 mt-1">活跃数据包</div>
          </div>
        </div>

        {/* Model registry */}
        <div className="card mb-4">
          <div className="card-header">模型注册表</div>
          {models.length === 0 ? (
            <p className="text-sm text-gray-400">暂无已注册模型</p>
          ) : (
            <table className="table-auto">
              <thead>
                <tr>
                  <th>模型名称</th>
                  <th>任务</th>
                  <th>版本</th>
                  <th>mAP@50</th>
                  <th>mAP@50-95</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m, i) => (
                  <tr key={m.name || i}>
                    <td className="font-medium">{m.name || m.version || `模型 #${i + 1}`}</td>
                    <td>{m.task || "—"}</td>
                    <td className="font-mono text-xs">{m.version || "—"}</td>
                    <td className="font-mono">{m.metrics?.map50?.toFixed(4) || "—"}</td>
                    <td className="font-mono">{m.metrics?.map50_95?.toFixed(4) || "—"}</td>
                    <td><Badge variant={m.status === "production" ? "success" : "info"}>{m.status || "experiment"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent training records */}
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <span>最近训练记录</span>
            <Link to="/models/training/records" className="text-blue-600 text-sm hover:underline">查看全部 →</Link>
          </div>
          {records.length === 0 ? (
            <p className="text-sm text-gray-400">暂无训练记录</p>
          ) : (
            <table className="table-auto">
              <thead>
                <tr><th>Job ID</th><th>操作</th><th>状态</th><th>时间</th></tr>
              </thead>
              <tbody>
                {records.slice(0, 5).map((r) => (
                  <tr key={r.id as string}>
                    <td className="font-mono text-xs">{(r.id as string).slice(0, 16)}...</td>
                    <td>{r.action as string}</td>
                    <td><Badge variant={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "warning"}>{r.status as string}</Badge></td>
                    <td className="text-xs text-gray-500">{r.created_at as string}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Quick actions */}
        <div className="flex gap-2 mt-4">
          <Link to="/models/training/submit"><Button variant="primary" size="small">提交训练</Button></Link>
          <Link to="/models/evaluation"><Button variant="default" size="small">查看评估</Button></Link>
          <Link to="/models/promotion"><Button variant="default" size="small">模型晋级</Button></Link>
        </div>
      </PageQueryState>
    </div>
  );
};
