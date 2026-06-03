import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";

type DashboardData = {
  stages: Record<string, number>; total_batches: number; pending_approvals: number;
  running_jobs: number; model_count: number; fleet: Record<string, unknown>;
  activity: Record<string, unknown>[]; recent_training: Record<string, unknown>[];
};

export const DashboardPage: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/dashboard", {
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${hsapApi.getToken()}` },
      cache: "no-store",
    }).then((r) => r.json()).then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>数据闭环</h1>
        <p>双数据源驱动 — T-Box 实采 + 世界模型仿真</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        {data && (
          <>
            {/* Pipeline flow visualization */}
            <div className="card mb-6">
              <div className="card-header">数据流入管线</div>
              <div className="flex items-center gap-0 text-sm py-4">
                {/* Left: T-Box */}
                <div className="flex-1 text-center">
                  <Link to="/fleet/dashboard" className="block p-4 rounded-xl border-2 border-blue-200 bg-blue-50/50 hover:border-blue-400 transition-colors">
                    <div className="text-3xl mb-2">🚛</div>
                    <div className="font-semibold text-blue-800">T-Box 实采</div>
                    <div className="text-xs text-gray-500 mt-1">车队采集 · GPS 标注</div>
                    <div className="text-xs text-blue-600 mt-1">
                      {data.fleet?.active_vehicles != null ? `${data.fleet.active_vehicles} 辆在线` : "—"}
                    </div>
                  </Link>
                  <div className="mt-2 text-xs text-gray-400">多帧视频 → 预处理 → 入库</div>
                </div>

                {/* Arrow */}
                <div className="text-gray-300 text-2xl px-2">→</div>

                {/* Middle: Processing */}
                <div className="flex-1 text-center">
                  <div className="p-4 rounded-xl border-2 border-gray-200 bg-gray-50/50">
                    <div className="text-3xl mb-2">⚙️</div>
                    <div className="font-semibold text-gray-700">数据加工</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {data.stages.out_for_labeling || 0} 标中 · {data.stages.returned || 0} 待入库
                    </div>
                    <div className="text-xs text-gray-400 mt-1">{data.total_batches} 个批次</div>
                  </div>
                  <div className="mt-2 text-xs text-gray-400">标注 → 质检 → 入库 → build</div>
                </div>

                {/* Arrow */}
                <div className="text-gray-300 text-2xl px-2">→</div>

                {/* Right: Training */}
                <div className="flex-1 text-center">
                  <Link to="/models/overview" className="block p-4 rounded-xl border-2 border-green-200 bg-green-50/50 hover:border-green-400 transition-colors">
                    <div className="text-3xl mb-2">🧠</div>
                    <div className="font-semibold text-green-800">模型训练</div>
                    <div className="text-xs text-gray-500 mt-1">{data.model_count} 个模型</div>
                    <div className="text-xs text-green-600 mt-1">{data.running_jobs} 个执行中</div>
                  </Link>
                  <div className="mt-2 text-xs text-gray-400">train → eval → promote</div>
                </div>

                {/* Rightmost: World Model */}
                <div className="text-gray-300 text-2xl px-2">↻</div>

                <div className="flex-1 text-center">
                  <Link to="/labeling/simulate" className="block p-4 rounded-xl border-2 border-purple-200 bg-purple-50/50 hover:border-purple-400 transition-colors">
                    <div className="text-3xl mb-2">🌐</div>
                    <div className="font-semibold text-purple-800">世界模型仿真</div>
                    <div className="text-xs text-gray-500 mt-1">场景生成 · 自动标注</div>
                    <div className="text-xs text-purple-600 mt-1">补数据缺口</div>
                  </Link>
                  <div className="mt-2 text-xs text-gray-400">评估反馈 → 生成 → 直接入库</div>
                </div>
              </div>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-5 gap-4 mb-6">
              <Link to="/labeling/workbench" className="card text-center hover:shadow-sm transition-shadow">
                <div className="text-2xl font-bold text-blue-700">{data.total_batches}</div>
                <div className="text-xs text-gray-500 mt-1">总批次</div>
              </Link>
              <Link to="/system/audit" className="card text-center hover:shadow-sm transition-shadow">
                <div className="text-2xl font-bold text-orange-600">{data.pending_approvals}</div>
                <div className="text-xs text-gray-500 mt-1">待审核</div>
              </Link>
              <Link to="/models/overview" className="card text-center hover:shadow-sm transition-shadow">
                <div className="text-2xl font-bold text-green-600">{data.model_count}</div>
                <div className="text-xs text-gray-500 mt-1">模型</div>
              </Link>
              <Link to="/system/jobs" className="card text-center hover:shadow-sm transition-shadow">
                <div className="text-2xl font-bold text-purple-600">{data.running_jobs}</div>
                <div className="text-xs text-gray-500 mt-1">执行中</div>
              </Link>
              <Link to="/fleet/dashboard" className="card text-center hover:shadow-sm transition-shadow">
                <div className="text-2xl font-bold text-gray-600">
                  {data.fleet?.active_vehicles != null ? String(data.fleet.active_vehicles) : "—"}
                </div>
                <div className="text-xs text-gray-500 mt-1">在线车辆</div>
              </Link>
            </div>

            {/* Stage distribution + Activity */}
            <div className="grid grid-cols-2 gap-6">
              <div className="card">
                <div className="card-header">批次阶段分布</div>
                <div className="space-y-2">
                  {[
                    { k: "raw_pool", label: "待送标", color: "bg-gray-400" },
                    { k: "out_for_labeling", label: "标中", color: "bg-blue-500" },
                    { k: "in_review", label: "质检中", color: "bg-yellow-500" },
                    { k: "review_approved", label: "已通过", color: "bg-green-500" },
                    { k: "returned", label: "已入库", color: "bg-green-600" },
                  ].map(({ k, label, color }) => {
                    const v = data.stages[k] || 0;
                    const max = Math.max(...Object.values(data.stages), 1);
                    return (
                      <div key={k} className="flex items-center gap-3 text-sm">
                        <span className="w-14 text-gray-500">{label}</span>
                        <div className="flex-1 h-4 bg-gray-100 rounded overflow-hidden">
                          <div className={`h-full rounded transition-all ${color}`} style={{ width: `${(v / max) * 100}%` }} />
                        </div>
                        <span className="w-6 text-right font-mono font-semibold text-sm">{v}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="card">
                <div className="card-header">快捷入口</div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <Link to="/labeling/workbench" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">📋</span> 送标工作台
                  </Link>
                  <Link to="/labeling/simulate" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-purple-50 transition-colors">
                    <span className="text-lg">🌐</span> 仿真工坊
                  </Link>
                  <Link to="/labeling/campaigns" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">✏️</span> 标注进度
                  </Link>
                  <Link to="/labeling/review" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">✅</span> 标注质检
                  </Link>
                  <Link to="/models/training/submit" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">🚀</span> 训练提交
                  </Link>
                  <Link to="/system/audit" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">📝</span> 审核队列
                  </Link>
                  <Link to="/fleet/dashboard" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">🚛</span> 车队总览
                  </Link>
                  <Link to="/models/datasets" className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <span className="text-lg">📦</span> 数据集版本
                  </Link>
                </div>
              </div>
            </div>

            {/* Data source summary */}
            <div className="grid grid-cols-2 gap-4 mt-6">
              <div className="card border-l-4 border-l-blue-500">
                <div className="text-xs text-gray-400 mb-1">T-Box 实采数据流</div>
                <div className="text-sm text-gray-600">
                  采集车多帧视频 → 预处理去噪去重 → 入库 →
                  标注 → 质检 → build → 模型训练
                </div>
              </div>
              <div className="card border-l-4 border-l-purple-500">
                <div className="text-xs text-gray-400 mb-1">世界模型仿真数据流</div>
                <div className="text-sm text-gray-600">
                  评估反馈(数据缺口) → 场景配置 → 生成 →
                  自动标注 → 直接入库 → 补充训练
                </div>
              </div>
            </div>
          </>
        )}
      </PageQueryState>
    </div>
  );
};
