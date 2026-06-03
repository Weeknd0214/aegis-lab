import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StageBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import type { LabelingBatchRow } from "@/lib/types";

export const CampaignsPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const filtered = batches.filter((b) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (b.batch || "").toLowerCase().includes(q) || (b.task || "").toLowerCase().includes(q) || (b.campaign_id || "").toLowerCase().includes(q);
  });

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await hsapApi.labelingBatches({ stage: "out_for_labeling", limit: 100 });
      setBatches((res.items || []) as LabelingBatchRow[]);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleExport = async (campaignId: string) => {
    setInfo(null);
    try { await hsapApi.labelingExport(campaignId); setInfo("导出任务已提交"); }
    catch (e) { setError(String(e)); }
  };

  const handleSubmit = async (campaignId: string) => {
    try { await hsapApi.submitLabelingCampaign(campaignId); load(); }
    catch (e) { setError(String(e)); }
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>标注进度</h1>
          <p>查看和管理进行中的标注活动</p>
        </div>
        <Button size="small" variant="default" onClick={load}>刷新</Button>
      </div>

      {/* Search */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-[200px] relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="搜索批次、任务或 Campaign ID..." value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">{filtered.length} 条</span>
        </div>
      </div>

      {info && <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 text-sm text-green-700">{info}</div>}

      <PageQueryState loading={loading} error={error} empty={filtered.length === 0} emptyMessage="暂无进行中的标注活动">
        <div className="space-y-3">
          {filtered.map((b) => {
            const pct = b.total_tasks && b.total_tasks > 0 ? Math.round(((b.completed_tasks || 0) / b.total_tasks) * 100) : 0;
            return (
              <div key={b.campaign_id || b.batch} className="card hover:shadow-sm transition-shadow">
                <div className="flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm">{b.batch}</span>
                      <span className="text-xs text-gray-400 font-mono">{b.task || "—"}</span>
                      <StageBadge stage={b.stage} />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-400">
                      {b.campaign_id && <span className="font-mono">{b.campaign_id.slice(0, 14)}...</span>}
                      {b.assigned_to_name && <span>👤 {b.assigned_to_name}</span>}
                    </div>
                    {b.total_tasks != null && b.total_tasks > 0 && (
                      <div className="mt-2 flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden max-w-[200px]">
                          <div className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-green-500" : "bg-blue-500"}`} style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs text-gray-500">{b.completed_tasks}/{b.total_tasks}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {b.campaign_id && (
                      <>
                        <a href={`/labeling/campaigns/${encodeURIComponent(b.campaign_id)}/annotate`} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors">
                          ✏️ 标注
                        </a>
                        <button onClick={() => handleExport(b.campaign_id!)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-50 text-gray-600 hover:bg-gray-100 transition-colors">
                          📤 导出
                        </button>
                        <button onClick={() => handleSubmit(b.campaign_id!)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-50 text-green-700 hover:bg-green-100 transition-colors">
                          ✅ 提交
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </PageQueryState>
    </div>
  );
};
