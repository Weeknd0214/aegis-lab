import React, { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";

interface MyAssignmentRow {
  campaign_id: string;
  batch: string;
  task: string;
  project?: string;
  status?: string;
  assigned: number;
  completed: number;
  pending: number;
  campaign_total?: number;
  annotate_url?: string;
}

export const MyTasksPage: React.FC = () => {
  const location = useLocation();
  const highlightId = new URLSearchParams(location.search).get("campaign");

  const [items, setItems] = useState<MyAssignmentRow[]>([]);
  const [totalPending, setTotalPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.myAssignments();
      setItems((res.items || []) as MyAssignmentRow[]);
      setTotalPending(res.total_pending ?? 0);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>我的标注</h1>
          <p>
            分配给您的标注任务
            {totalPending > 0 && (
              <span className="text-amber-600 font-medium"> · 待标 {totalPending} 张</span>
            )}
          </p>
        </div>
        <Button size="small" variant="default" onClick={load}>
          刷新
        </Button>
      </div>

      <PageQueryState
        loading={loading}
        error={error}
        empty={items.length === 0}
        emptyMessage="暂无分配给您的任务，请联系协调员分配或等待飞书通知"
      >
        <div className="space-y-3">
          {items.map((row) => {
            const pct = row.assigned > 0 ? Math.round((row.completed / row.assigned) * 100) : 0;
            const highlighted = highlightId === row.campaign_id;
            return (
              <div
                key={row.campaign_id}
                className={`card transition-shadow ${
                  highlighted ? "ring-2 ring-blue-400 shadow-md" : "hover:shadow-sm"
                }`}
              >
                <div className="flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm">{row.batch}</span>
                      <span className="text-xs text-gray-400 font-mono">{row.task}</span>
                      {row.project && (
                        <span className="text-xs text-gray-400 uppercase">{row.project}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>
                        待标 <strong className="text-amber-600">{row.pending}</strong>
                      </span>
                      <span>已完成 {row.completed}</span>
                      <span>共分配 {row.assigned}</span>
                      {row.campaign_total != null && (
                        <span className="text-gray-400">批次共 {row.campaign_total} 张</span>
                      )}
                    </div>
                    <div className="mt-2 flex items-center gap-2 max-w-xs">
                      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${pct >= 100 ? "bg-green-500" : "bg-blue-500"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400">{pct}%</span>
                    </div>
                  </div>
                  <Link
                    to={`/labeling/annotate/${encodeURIComponent(row.campaign_id)}`}
                    className="shrink-0"
                  >
                    <Button size="small" variant="primary">
                      {row.pending > 0 ? "继续标注" : "查看"}
                    </Button>
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      </PageQueryState>
    </div>
  );
};
