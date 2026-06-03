import React, { useEffect, useState, useCallback } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Badge } from "@/components/ui/Badge";
import { Userpic } from "@/components/ui/Userpic";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";

type LogEntry = {
  id: number; timestamp: string; user_id: number; user_name: string;
  category: string; action: string; target_type: string; target_id: string;
  summary: string; detail: Record<string, unknown> | null; ip_address: string;
};

const CATEGORY_LABELS: Record<string, { label: string; color: "info" | "success" | "warning" | "danger" | "default" }> = {
  auth: { label: "认证", color: "info" },
  data: { label: "数据", color: "success" },
  labeling: { label: "标注", color: "warning" },
  audit: { label: "审核", color: "danger" },
  training: { label: "训练", color: "info" },
  system: { label: "系统", color: "default" },
};

export const AuditLogPage: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const load = useCallback(async (newOffset = 0, newLimit = 30) => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (search) params.set("search", search);
      params.set("offset", String(newOffset));
      params.set("limit", String(newLimit));
      const res = await fetch(`/api/v1/system/audit-log?${params}`, {
        headers: { Authorization: `Bearer ${hsapApi.getToken()}` },
        cache: "no-store",
      }).then((r) => r.json());
      setLogs((res.items || []) as LogEntry[]);
      setTotal(res.total);
      setOffset(newOffset); setLimit(newLimit);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, [category, search]);

  useEffect(() => { load(); }, [load]);

  const catBadge = (cat: string) => {
    const c = CATEGORY_LABELS[cat] || { label: cat, color: "default" as const };
    return <Badge variant={c.color} size="small">{c.label}</Badge>;
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>操作日志</h1>
        <p>平台所有关键操作的审计记录，保留 90 天</p>
      </div>

      <div className="flex gap-2 mb-3 flex-wrap">
        <select className="form-input w-auto" value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0); }}>
          <option value="">全部分类</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <input className="form-input w-48" placeholder="搜索用户/摘要..." value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
      </div>

      <PageQueryState loading={loading} error={error} empty={logs.length === 0} emptyMessage="暂无操作记录">
        <div className="card overflow-hidden">
          <div className="space-y-0 divide-y divide-gray-100">
            {logs.map((log) => (
              <div key={log.id} className="py-2.5 px-3 hover:bg-gray-50 transition-colors">
                <div className="flex items-center gap-3">
                  <Userpic username={log.user_name} size={28} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{log.user_name || "系统"}</span>
                      {catBadge(log.category)}
                      <span className="text-sm text-gray-700 truncate">{log.summary || log.action}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-400">
                      <span>{log.timestamp || "—"}</span>
                      {log.target_type && <span>· {log.target_type}/{log.target_id?.slice(0, 16)}</span>}
                      <button onClick={() => setExpandedId(expandedId === log.id ? null : log.id)} className="text-blue-500 hover:underline">
                        {expandedId === log.id ? "收起" : "详情"}
                      </button>
                    </div>
                    {expandedId === log.id && log.detail && (
                      <pre className="text-xs mt-1 bg-gray-50 p-2 rounded max-h-32 overflow-auto">
                        {JSON.stringify(log.detail, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <ListPaginationBar total={total} offset={offset} limit={limit}
            onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
        </div>
      </PageQueryState>
    </div>
  );
};
