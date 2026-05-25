import { useEffect, useState } from "react";
import { api, type JobRecord } from "../api/client";

export function JobsPage() {
  const [items, setItems] = useState<JobRecord[]>([]);
  useEffect(() => { api.listJobs().then((d) => setItems(d.items || [])); }, []);

  const badge = (s: string) =>
    ({ queued: "badge-pending", running: "badge-training", succeeded: "badge-evaluated", failed: "badge-pending" }[s] || "badge-idle");

  return (
    <div className="panel">
      <div className="panel-header"><h2>Job 队列</h2><span className="text-dim">{items.length} 项</span></div>
      <div className="panel-body table-wrap">
        <table className="data-table">
          <thead><tr><th>Job ID</th><th>动作</th><th>状态</th><th>审核单</th><th>开始</th><th>结果</th></tr></thead>
          <tbody>
            {items.map((j) => (
              <tr key={j.id}>
                <td className="mono text-sm">{j.id}</td>
                <td>{j.action}</td>
                <td><span className={`badge ${badge(j.status)}`}>{j.status}</span></td>
                <td>{j.approval_id || "—"}</td>
                <td className="text-sm">{j.started_at?.slice(0, 19)}</td>
                <td className="text-sm">{j.result?.error || (j.result?.ok ? "ok" : "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
