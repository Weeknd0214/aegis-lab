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
  const [info, setInfo] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [statsMap, setStatsMap] = useState<Record<string, Record<string, unknown>>>({});
  const [buildingId, setBuildingId] = useState<string | null>(null);
  const [fittingId, setFittingId] = useState<string | null>(null);
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
      const adasReturned = results.filter((b) => b.stage === "returned" && b.project === "adas" && b.campaign_id);
      if (adasReturned.length) {
        const entries = await Promise.allSettled(
          adasReturned.map(async (b) => {
            const s = await hsapApi.labelingExportStats(b.campaign_id!);
            return [b.campaign_id!, s] as const;
          }),
        );
        const map: Record<string, Record<string, unknown>> = {};
        for (const e of entries) {
          if (e.status === "fulfilled") map[e.value[0]] = e.value[1];
        }
        setStatsMap(map);
      }
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleExport = async (campaignId: string) => {
    try { await hsapApi.labelingExport(campaignId); setInfo("导出任务已提交"); load(); }
    catch (e) { setError(String(e)); }
  };

  const handleCuboidFit = async (campaignId: string) => {
    setFittingId(campaignId);
    try {
      await hsapApi.cuboidFit(campaignId);
      setInfo("3D 拟合任务已提交");
      load();
    } catch (e) { setError(String(e)); }
    setFittingId(null);
  };

  const handleSubmitBuild = async (b: LabelingBatchRow) => {
    if (!b.task || !b.batch) return;
    setBuildingId(b.campaign_id || b.batch);
    setError(null);
    try {
      await hsapApi.submitBuildBatch({
        project: b.project || "dms",
        task: b.task,
        batch: b.batch,
        pack: b.pack || (b.project === "adas" ? "adas_moon3d_v1" : "dms_v2"),
        location: b.location || "inbox",
        note: `入库 ${b.batch}`,
      });
      setInfo("build 已提交至审核队列");
      load();
    } catch (e) {
      setError(String(e));
    }
    setBuildingId(null);
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
        <p>质检通过后的格式转换、供应商回标、build 入库</p>
      </div>

      {info && <div className="bg-green-50 border border-green-200 rounded p-3 mb-4 text-sm text-green-700">{info}</div>}

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
            {["全部", "待导出", "待 build"].map((label, i) => {
              const val = i === 0 ? "" : ["labeling_submitted", "returned"][i - 1];
              return <button key={val} onClick={() => setStageFilter(val)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${stageFilter === val ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>{label}</button>;
            })}
          </div>
          <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">{filtered.length} 条</span>
        </div>
      </div>

      <div className="card mb-4">
        <div className="card-header">流程说明</div>
        <div className="text-sm text-gray-600 space-y-2">
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">1</span>
            <span><strong>提交质检</strong> — 标注员完成标注后，在标注进度页点击「提交质检」</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">2</span>
            <span><strong>质检通过</strong> — 协调员在质检页审核，通过后批次进入「待导出」</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-orange-100 text-orange-700 flex items-center justify-center text-xs font-bold">3</span>
            <span>
              <strong>执行导出</strong> — 将 CVAT 标注转为训练格式（DMS→YOLO，ADAS→quaternion_json）
              {hasData && <span className="text-gray-400">（下表有待处理批次）</span>}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-xs font-bold">4</span>
            <span>
              <strong>提交 build</strong> — 导出完成后进入 <Badge variant="warning" size="small">待 build</Badge>，在此提交 build 并经审核队列批准后变为 <Badge variant="success" size="small">已入库</Badge>
              <span className="block text-xs text-gray-400 mt-0.5">「待 build」≠「已入库」；ingested 批次不会出现在本页</span>
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
                      <span className="text-xs text-gray-400">{b.project}/{b.task || "—"}</span>
                      <Badge variant={b.stage === "returned" ? "warning" : "warning"}>{b.stage === "labeling_submitted" ? "待导出" : "待 build"}</Badge>
                    </div>
                    <div className="text-xs text-gray-400 font-mono mt-1">{b.campaign_id?.slice(0, 16) || "—"}</div>
                    {b.stage === "returned" && b.project === "adas" && b.campaign_id && statsMap[b.campaign_id] && (
                      <div className="text-xs text-gray-500 mt-1">
                        quaternion: {String(statsMap[b.campaign_id].quaternion_files ?? "—")} ·
                        fit_ok: {((Number(statsMap[b.campaign_id].fit_ok_ratio) || 0) * 100).toFixed(0)}% ·
                        pack: adas_moon3d_v1
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {b.campaign_id && b.stage === "labeling_submitted" && (
                      <>
                        <Button size="small" variant="primary" onClick={() => handleExport(b.campaign_id!)}>📤 执行导出</Button>
                        <Button size="small" variant="default" loading={importingId === b.campaign_id} onClick={() => handleImportVendor(b.campaign_id!)}>📥 导入供应商</Button>
                      </>
                    )}
                    {b.stage === "returned" && (
                      <>
                        {b.project === "adas" && b.campaign_id && (
                          <Button size="small" variant="default" loading={fittingId === b.campaign_id} onClick={() => handleCuboidFit(b.campaign_id!)}>
                            补全 3D
                          </Button>
                        )}
                        <Button
                          size="small"
                          variant="primary"
                          loading={buildingId === (b.campaign_id || b.batch)}
                          onClick={() => handleSubmitBuild(b)}
                        >
                          🏗 提交 build
                        </Button>
                        <Link to="/system/audit" className="text-xs text-blue-600 hover:underline">审核队列 →</Link>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="card text-center py-12">
            <p className="text-gray-400 text-lg mb-3">暂无待导出或待 build 的批次</p>
            <p className="text-gray-400 text-sm mb-4">完成标注并质检通过后，批次会出现在此处</p>
            <Link to="/labeling/campaigns"><Button variant="default" size="small">去标注进度 →</Button></Link>
          </div>
        )}
      </PageQueryState>
    </div>
  );
};
