import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";
import { Badge } from "@/components/ui/Badge";
import type { LabelingBatchRow } from "@/lib/types";

export const ExportPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");

  const filtered = batches.filter((b) => {
    if (search && !(b.batch || "").toLowerCase().includes(search.toLowerCase()) && !(b.task || "").toLowerCase().includes(search.toLowerCase())) return false;
    if (stageFilter && b.stage !== stageFilter) return false;
    return true;
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results: LabelingBatchRow[] = [];
      const [submitted, returned] = await Promise.allSettled([
        hsapApi.labelingBatches({ stage: "labeling_submitted", limit: 100 }),
        hsapApi.labelingBatches({ stage: "returned", limit: 100 }),
      ]);
      if (submitted.status === "fulfilled") results.push(...((submitted.value.items || []) as LabelingBatchRow[]));
      if (returned.status === "fulfilled") results.push(...((returned.value.items || []) as LabelingBatchRow[]));
      if (submitted.status === "rejected" && returned.status === "rejected") setError(String(submitted.reason));
      setBatches(results);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleExport = async (campaignId: string) => {
    try { await hsapApi.labelingExport(campaignId); load(); }
    catch (e) { setError(String(e)); }
  };

  const handleImportVendor = async (campaignId: string) => {
    const input = document.createElement("input");
    input.type = "file"; input.accept = ".zip";
    input.onchange = async (e) => {
      const f = (e.target as HTMLInputElement).files?.[0];
      if (!f) return;
      setImportingId(campaignId);
      try { await hsapApi.importVendorZip(campaignId, f); load(); }
      catch (err) { setError(String(err)); }
      setImportingId(null);
    };
    input.click();
  };

  const hasData = batches.length > 0;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>导出与入库</h1>
        <p>标注完成后的导出、供应商回标导入、入库流程</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-[200px] relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="搜索批次/任务..." value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="flex gap-1.5">
            {["全部", "待导出", "待入库"].map((label, i) => {
              const val = i === 0 ? "" : ["labeling_submitted", "returned"][i - 1];
              return <button key={val} onClick={() => setStageFilter(val)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${stageFilter === val ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>{label}</button>;
            })}
          </div>
          <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">{filtered.length} 条</span>
        </div>
      </div>

      {/* Workflow guide */}
      <div className="card mb-4">
        <div className="card-header">流程说明</div>
        <div className="text-sm text-gray-600 space-y-2">
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">1</span>
            <span><strong>标注提交</strong> — 标注员在 Campaign 中完成标注后，点击"提交批次"</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">2</span>
            <span>
              <strong>导出标注</strong> — 在此页面点击"执行导出"，将标注结果转为 YOLO 格式
              {hasData && <span className="text-gray-400">（下表有待导出批次）</span>}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-orange-100 text-orange-700 flex items-center justify-center text-xs font-bold">3</span>
            <span>
              <strong>供应商回标</strong> — 如果是外部供应商标注的，点击"导入供应商"上传 ZIP 回标文件
              <span className="block text-xs text-gray-400 mt-0.5">ZIP 格式要求：每张图片对应一个同名 .txt 标注文件（YOLO 格式），放在同一目录下打包</span>
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-xs font-bold">4</span>
            <span>
              <strong>入库 build</strong> — 导出完成后，批次进入 <Badge variant="success" size="small">待入库</Badge> 状态，可通过审核队列提交 build
              <span className="block text-xs text-gray-400 mt-0.5">build 成功后自动生成数据集版本快照</span>
            </span>
          </div>
        </div>
      </div>

      <PageQueryState loading={loading} error={error} empty={filtered.length === 0}>
        {filtered.length > 0 ? (
          <div className="space-y-2">
            {filtered.map((b) => (
              <div key={b.campaign_id || b.batch} className="card hover:shadow-sm transition-shadow">
                <div className="flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm">{b.batch}</span>
                      <span className="text-xs text-gray-400">{b.task || "—"}</span>
                      <Badge variant={b.stage === "returned" ? "success" : "warning"}>{b.stage === "labeling_submitted" ? "待导出" : "待入库"}</Badge>
                    </div>
                    <div className="text-xs text-gray-400 font-mono mt-1">{b.campaign_id?.slice(0, 16) || "—"}</div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {b.campaign_id && b.stage === "labeling_submitted" && (
                      <>
                        <Button size="small" variant="primary" onClick={() => handleExport(b.campaign_id!)}>📤 执行导出</Button>
                        <Button size="small" variant="default" loading={importingId === b.campaign_id} onClick={() => handleImportVendor(b.campaign_id!)}>📥 导入供应商</Button>
                      </>
                    )}
                    {b.stage === "returned" && <span className="text-green-600 text-sm font-medium">✓ 已入库</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="card text-center py-12">
            <p className="text-gray-400 text-lg mb-3">暂无待导出或待入库的批次</p>
            <p className="text-gray-400 text-sm mb-4">完成标注后，在标注进度页提交批次，即可在此处导出</p>
            <Link to="/labeling/campaigns"><Button variant="default" size="small">去标注进度 →</Button></Link>
          </div>
        )}
      </PageQueryState>
    </div>
  );
};
