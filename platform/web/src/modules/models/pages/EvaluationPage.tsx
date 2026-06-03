import React, { useEffect, useState, useMemo } from "react";
import { hsapApi } from "@/app/hsap-api";
import { StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";

type EvalRecord = Record<string, unknown>;

export const EvaluationPage: React.FC = () => {
  const [records, setRecords] = useState<EvalRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = async (newOffset = 0, newLimit = 20) => {
    setLoading(true); setError(null);
    try {
      const res = await hsapApi.listTrainingRecords({ offset: newOffset, limit: newLimit });
      const all = (res.items || []) as EvalRecord[];
      const evalRecs = all.filter((r) => {
        const a = (r.action as string || "").toLowerCase();
        return a.includes("eval") || a.includes("promote");
      });
      setRecords(evalRecs);
      setTotal(evalRecs.length);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  // Extract metric data for chart
  const metricData = useMemo(() => {
    const data: { label: string; map50: number; map50_95: number }[] = [];
    for (const r of records) {
      const result = r.result as Record<string, unknown> | undefined;
      const metrics = result?.metrics as Record<string, number> | undefined;
      if (metrics?.map50 != null) {
        data.push({
          label: `${r.task || "?"}/${r.pack || "?"}`.slice(0, 24),
          map50: metrics.map50,
          map50_95: metrics.map50_95 ?? 0,
        });
      }
    }
    return data;
  }, [records]);

  const maxMap50 = Math.max(...metricData.map((d) => d.map50), 0.01);

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>评估管理</h1>
        <p>模型评估结果与指标对比</p>
      </div>

      {/* mAP comparison bar chart */}
      {metricData.length > 0 && (
        <div className="card mb-4">
          <div className="card-header">mAP 指标对比</div>
          <div className="space-y-2">
            {metricData.map((d, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className="w-32 truncate font-mono text-xs text-gray-500" title={d.label}>{d.label}</span>
                <div className="flex-1 flex items-center gap-1">
                  <div className="flex-1 h-5 bg-gray-100 rounded relative overflow-hidden">
                    <div className="absolute inset-y-0 left-0 bg-blue-600 rounded" style={{ width: `${(d.map50 / maxMap50) * 100}%` }} />
                  </div>
                  <span className="w-14 text-right font-mono text-xs">{d.map50.toFixed(3)}</span>
                </div>
                {d.map50_95 > 0 && (
                  <div className="flex items-center gap-1 flex-1">
                    <span className="text-[10px] text-gray-400 w-16 text-right">mAP50-95</span>
                    <div className="flex-1 h-4 bg-gray-100 rounded relative overflow-hidden">
                      <div className="absolute inset-y-0 left-0 bg-green-500 rounded" style={{ width: `${(d.map50_95 / maxMap50) * 100}%` }} />
                    </div>
                    <span className="w-14 text-right font-mono text-xs">{d.map50_95.toFixed(3)}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evaluation record list */}
      <PageQueryState loading={loading} error={error} empty={records.length === 0} emptyMessage="暂无评估记录">
        <div className="card overflow-hidden">
          <table className="table-auto">
            <thead>
              <tr>
                <th className="w-8" />
                <th>Job ID</th>
                <th>项目</th>
                <th>任务</th>
                <th>操作</th>
                <th>状态</th>
                <th>mAP@50</th>
                <th>mAP@50-95</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => {
                const rid = r.id as string;
                const result = r.result as Record<string, unknown> | undefined;
                const metrics = result?.metrics as Record<string, number> | undefined;
                return (
                  <React.Fragment key={rid}>
                    <tr className={expandedId === rid ? "bg-blue-50/50" : ""}>
                      <td>
                        <button onClick={() => setExpandedId(expandedId === rid ? null : rid)} className="text-gray-400 hover:text-blue-600 text-xs px-1">
                          {expandedId === rid ? "▼" : "▶"}
                        </button>
                      </td>
                      <td className="font-mono text-xs">{rid.slice(0, 16)}...</td>
                      <td>{r.project as string || "—"}</td>
                      <td>{r.task as string || "—"}</td>
                      <td>{r.action as string || "—"}</td>
                      <td><StatusBadge status={(r.status as string) || "pending"} /></td>
                      <td className="font-mono text-xs">{metrics?.map50?.toFixed(4) || "—"}</td>
                      <td className="font-mono text-xs">{metrics?.map50_95?.toFixed(4) || "—"}</td>
                      <td className="text-xs text-gray-500">{r.created_at as string || "—"}</td>
                    </tr>
                    {expandedId === rid && (
                      <tr>
                        <td colSpan={9} className="bg-gray-50 p-4">
                          {result ? (
                            <pre className="text-xs bg-white border rounded p-3 max-h-48 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
                          ) : <p className="text-gray-400 text-sm">暂无详细结果</p>}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          <ListPaginationBar total={total} offset={offset} limit={limit} onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
        </div>
      </PageQueryState>
    </div>
  );
};
