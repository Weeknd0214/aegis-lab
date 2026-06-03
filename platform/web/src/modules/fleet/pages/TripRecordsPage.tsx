import React, { useEffect, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StatusBadge, Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";

export const TripRecordsPage: React.FC = () => {
  const [runs, setRuns] = useState<Record<string, unknown>[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (newOffset = 0, newLimit = 20) => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.fleetRuns({ offset: newOffset, limit: newLimit });
      setRuns((res.items || []) as Record<string, unknown>[]);
      setTotal(res.total);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleImportGpx = async (vehicleId: number) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".gpx";
    input.onchange = async (e) => {
      const f = (e.target as HTMLInputElement).files?.[0];
      if (!f) return;
      try {
        await hsapApi.fleetImportGpx(vehicleId, f);
        load(0, limit);
      } catch (err) {
        setError(String(err));
      }
    };
    input.click();
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>行程记录</h1>
        <p>查看车辆采集行程历史</p>
      </div>

      <PageQueryState loading={loading} error={error} empty={runs.length === 0} emptyMessage="暂无行程记录">
        <div className="card">
          <table className="table-auto">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>车辆</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>结束时间</th>
                <th>里程 (km)</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id as number}>
                  <td className="font-mono text-xs">{String(r.id)}</td>
                  <td>{(r.plate_no as string) || `ID:${r.vehicle_id}`}</td>
                  <td><StatusBadge status={(r.status as string) || "pending"} /></td>
                  <td className="text-xs text-gray-500">{r.started_at as string || "—"}</td>
                  <td className="text-xs text-gray-500">{r.ended_at as string || "—"}</td>
                  <td>{r.total_km != null ? `${Number(r.total_km).toFixed(1)}` : "—"}</td>
                  <td className="flex gap-2">
                    <Button size="small" variant="default" onClick={() => handleImportGpx(r.vehicle_id as number)}>
                      导入 GPX
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
