import { useEffect, useState } from "react";
import { api, type PendingReport } from "../api/client";

export function LogsPage() {
  const [pending, setPending] = useState<PendingReport | null>(null);
  useEffect(() => { api.pending().then(setPending); }, []);

  const recent = pending?.projects?.dms?.recent_ingest || [];

  return (
    <>
      <div className="panel">
        <div className="panel-header"><h2>ingest_log.jsonl（最近）</h2></div>
        <div className="panel-body log-list">
          {recent.length ? recent.map((l, i) => (
            <div key={i} className="log-entry">
              <span className="log-time">{l.ts}</span>
              <span className="log-type ingest">ingest</span>
              <span>task={l.task} pack={l.pack} added={l.added ?? "—"}</span>
            </div>
          )) : <p className="empty-state">暂无记录</p>}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><h2>approval_queue.jsonl</h2></div>
        <div className="panel-body"><p className="mono text-sm">HSAP/manifests/approval_queue.jsonl</p></div>
      </div>
    </>
  );
}
