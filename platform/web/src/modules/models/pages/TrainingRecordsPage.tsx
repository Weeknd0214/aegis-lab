import React, { useEffect, useState, useCallback } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StatusBadge, Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";

type TrainingRecord = Record<string, unknown>;

export const TrainingRecordsPage: React.FC = () => {
  const [records, setRecords] = useState<TrainingRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, TrainingRecord | null>>({});

  const load = useCallback(async (newOffset = 0, newLimit = 20) => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.listTrainingRecords({
        project: project || undefined,
        status: status || undefined,
        offset: newOffset,
        limit: newLimit,
      });
      setRecords((res.items || []) as TrainingRecord[]);
      setTotal(res.total);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [project, status]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 15 seconds
  useEffect(() => {
    const t = setInterval(() => load(offset, limit), 15000);
    return () => clearInterval(t);
  }, [load, offset, limit]);

  const handleToggleDetail = async (jobId: string) => {
    if (expandedId === jobId) { setExpandedId(null); return; }
    setExpandedId(jobId);
    if (!detailCache[jobId]) {
      try {
        const detail = await hsapApi.getTrainingRecord(jobId);
        setDetailCache((prev) => ({ ...prev, [jobId]: detail }));
      } catch {
        setDetailCache((prev) => ({ ...prev, [jobId]: null }));
      }
    }
  };

  const detail = expandedId ? detailCache[expandedId] : null;

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>训练记录</h1>
          <p>查看所有训练/评估任务，每 15 秒自动刷新</p>
        </div>
        <Button size="small" variant="default" onClick={() => load(offset, limit)}>手动刷新</Button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4 flex-wrap">
        <input className="form-input w-44" placeholder="搜索 Job ID/任务..." value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        <select className="form-input w-auto" value={project} onChange={(e) => { setProject(e.target.value); setOffset(0); }}>
          <option value="">全部项目</option>
          <option value="dms">DMS</option>
          <option value="lane">Lane</option>
        </select>
        <select className="form-input w-auto" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">全部状态</option>
          <option value="pending">待审核</option>
          <option value="approved">已通过</option>
          <option value="running">执行中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
        </select>
      </div>

      <PageQueryState loading={loading} error={error} empty={records.length === 0} emptyMessage="暂无训练记录">
        <div className="card overflow-hidden">
          <table className="table-auto">
            <thead>
              <tr>
                <th className="w-10" />
                <th>Job ID</th>
                <th>项目</th>
                <th>任务</th>
                <th>操作</th>
                <th>状态</th>
                <th>数据包</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => {
                const rid = r.id as string;
                const isExpanded = expandedId === rid;
                return (
                  <React.Fragment key={rid}>
                    <tr className={isExpanded ? "bg-blue-50/50" : ""}>
                      <td>
                        <button onClick={() => handleToggleDetail(rid)} className="text-gray-400 hover:text-blue-600 text-xs px-1">
                          {isExpanded ? "▼" : "▶"}
                        </button>
                      </td>
                      <td className="font-mono text-xs">{rid.slice(0, 16)}...</td>
                      <td>{r.project as string || "—"}</td>
                      <td>{r.task as string || "—"}</td>
                      <td><Badge variant="info">{(r.action as string || "—").replace(/_/g, " ")}</Badge></td>
                      <td><StatusBadge status={(r.status as string) || "pending"} /></td>
                      <td className="text-xs font-mono">{r.pack as string || "—"}</td>
                      <td className="text-xs text-gray-500 whitespace-nowrap">{r.created_at as string || "—"}</td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${rid}-detail`}>
                        <td colSpan={8} className="bg-gray-50 p-4">
                          {detail === undefined ? (
                            <p className="text-gray-400 text-sm">加载中...</p>
                          ) : detail === null ? (
                            <p className="text-red-400 text-sm">加载失败</p>
                          ) : (
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <p className="font-semibold mb-2 text-gray-700">参数</p>
                                <pre className="text-xs bg-white border rounded p-3 max-h-48 overflow-auto">
                                  {JSON.stringify(detail.params || {}, null, 2)}
                                </pre>
                              </div>
                              <div>
                                <p className="font-semibold mb-2 text-gray-700">结果</p>
                                {detail.result ? (
                                  <pre className="text-xs bg-white border rounded p-3 max-h-48 overflow-auto">
                                    {JSON.stringify(detail.result, null, 2)}
                                  </pre>
                                ) : (
                                  <p className="text-xs text-gray-400">
                                    {detail.status === "running" ? "执行中..." : detail.status === "failed" ? `失败: ${detail.error || "未知错误"}` : "暂无结果"}
                                  </p>
                                )}
                              </div>
                              {detail.note != null && String(detail.note) && (
                                <div className="col-span-2">
                                  <p className="font-semibold mb-1 text-gray-700">备注</p>
                                  <p className="text-sm text-gray-600">{String(detail.note ?? "")}</p>
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          <ListPaginationBar total={total} offset={offset} limit={limit}
            onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
        </div>
      </PageQueryState>
    </div>
  );
};
