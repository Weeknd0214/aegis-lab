import React, { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";
import { MyTasksTable } from "../components/MyTasksTable";
import type { MyAssignmentRow } from "../components/MyTasksTable";

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
        <MyTasksTable items={items} highlightId={highlightId} />
      </PageQueryState>
    </div>
  );
};
