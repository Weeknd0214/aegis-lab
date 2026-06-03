import React, { useEffect, useState, useCallback } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";

export const JobMonitorPage: React.FC = () => {
  const [jobs, setJobs] = useState<Record<string, unknown>[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState("");

  const load = useCallback(async (newOffset = 0, newLimit = 20) => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.listJobs({
        status: filterStatus || undefined,
        offset: newOffset,
        limit: newLimit,
      });
      setJobs((res.items || []) as Record<string, unknown>[]);
      setTotal(res.total);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [filterStatus]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const t = setInterval(() => load(offset, limit), 10000);
    return () => clearInterval(t);
  }, [offset, limit, load]);

  const handleView = async (jobId: string) => {
    try {
      const job = await hsapApi.getJob(jobId);
      alert(JSON.stringify(job, null, 2));
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>任务监控</h1>
          <p>查看异步任务执行状态，每 10 秒自动刷新</p>
        </div>
        <Button size="small" variant="default" onClick={() => load(offset, limit)}>手动刷新</Button>
      </div>

      <div className="flex gap-2 mb-4">
        <select className="form-input w-auto" value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setOffset(0); }}>
          <option value="">全部状态</option>
          <option value="pending">等待中</option>
          <option value="running">执行中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
        </select>
      </div>

      <PageQueryState loading={loading} error={error} empty={jobs.length === 0} emptyMessage="暂无任务记录">
        <div className="card">
          <table className="table-auto">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>操作</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>完成时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id as string}>
                  <td className="font-mono text-xs">{(j.id as string || "").slice(0, 16)}...</td>
                  <td>{j.action as string || "—"}</td>
                  <td><StatusBadge status={(j.status as string) || "pending"} /></td>
                  <td className="text-xs text-gray-500">{j.created_at as string || "—"}</td>
                  <td className="text-xs text-gray-500">{j.completed_at as string || "—"}</td>
                  <td>
                    <Button size="small" variant="default" onClick={() => handleView(j.id as string)}>
                      详情
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ListPaginationBar total={total} offset={offset} limit={limit} onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
        </div>
      </PageQueryState>
    </div>
  );
};
