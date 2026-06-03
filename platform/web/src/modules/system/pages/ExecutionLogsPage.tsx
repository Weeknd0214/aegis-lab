import React, { useEffect, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";

export const ExecutionLogsPage: React.FC = () => {
  const [traces, setTraces] = useState<string[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTraces = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.listTraces(50);
      setTraces(res.trace_ids || []);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  };

  useEffect(() => { loadTraces(); }, []);

  const handleViewTrace = async (traceId: string) => {
    try {
      const t = await hsapApi.getTrace(traceId);
      setSelectedTrace(t);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>执行日志</h1>
        <p>Agent 执行 Trace 与 Span 日志查看</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Trace list */}
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <span>Trace 列表</span>
            <Button size="small" variant="default" onClick={loadTraces}>刷新</Button>
          </div>
          <PageQueryState loading={loading} error={error} empty={traces.length === 0} emptyMessage="暂无 Trace 记录">
            <div className="max-h-96 overflow-y-auto space-y-1">
              {traces.map((t) => (
                <button
                  key={t}
                  onClick={() => handleViewTrace(t)}
                  className={`w-full text-left px-3 py-2 text-xs font-mono rounded hover:bg-blue-50 transition-colors ${
                    selectedTrace && (selectedTrace.trace_id as string) === t ? "bg-blue-100 text-blue-800" : "text-gray-600"
                  }`}
                >
                  {t.slice(0, 32)}...
                </button>
              ))}
            </div>
          </PageQueryState>
        </div>

        {/* Trace detail */}
        <div className="card col-span-2">
          <div className="card-header">Trace 详情</div>
          {selectedTrace ? (
            <div>
              <p className="text-sm text-gray-500 mb-2 font-mono">
                Trace ID: {selectedTrace.trace_id as string}
              </p>
              <p className="text-sm text-gray-500 mb-4">
                Spans: {(selectedTrace.spans as unknown[])?.length || 0}
              </p>
              <pre className="text-xs overflow-auto max-h-96 bg-gray-50 p-3 rounded">
                {JSON.stringify(selectedTrace.spans, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-400 text-sm">
              请从左侧选择一个 Trace 查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
