import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import { LabelingListToolbar } from "../components/LabelingListToolbar";
import { ExportPipelineFlow } from "../components/ExportPipelineFlow";
import { ExportBatchTable } from "../components/ExportBatchTable";
import { defaultBuildPack } from "@/lib/labelingDisplay";
import type { LabelingBatchRow } from "@/lib/types";

export const ExportPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [buildingId, setBuildingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [pendingExport, setPendingExport] = useState(0);
  const [pendingBuild, setPendingBuild] = useState(0);

  const loadStageCounts = useCallback(async () => {
    try {
      const [sub, ret] = await Promise.all([
        hsapApi.labelingBatches({ stage: "labeling_submitted", limit: 1, offset: 0 }),
        hsapApi.labelingBatches({ stage: "returned", limit: 1, offset: 0 }),
      ]);
      setPendingExport(sub.total ?? 0);
      setPendingBuild(ret.total ?? 0);
    } catch { /* optional */ }
  }, []);

  const load = useCallback(async (newOffset: number, newLimit: number) => {
    setLoading(true);
    setError(null);
    try {
      const q = search.trim() || undefined;
      const res = await hsapApi.labelingBatches(
        stageFilter
          ? { stage: stageFilter, offset: newOffset, limit: newLimit, q }
          : { stages: ["labeling_submitted", "returned"], offset: newOffset, limit: newLimit, q },
      );
      setBatches((res.items || []) as LabelingBatchRow[]);
      setTotal(res.total ?? 0);
      setOffset(newOffset);
      setLimit(newLimit);
      await loadStageCounts();
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, [search, stageFilter, loadStageCounts]);

  useEffect(() => { void load(0, limit); }, [search, stageFilter]);

  const reloadCurrent = useCallback(() => load(offset, limit), [load, offset, limit]);

  const handleExport = async (campaignId: string) => {
    try { await hsapApi.labelingExport(campaignId); setInfo("导出任务已提交"); reloadCurrent(); }
    catch (e) { setError(String(e)); }
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
        pack: defaultBuildPack(b),
        location: b.location || "inbox",
        note: `入库 ${b.batch}`,
      });
      setInfo("入库任务已提交至审核队列");
      reloadCurrent();
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
      try { await hsapApi.importVendorZip(campaignId, f); reloadCurrent(); }
      catch (err) { setError(String(err)); }
      setImportingId(null);
    };
    input.click();
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between gap-4">
        <div>
          <h1>导出与入库</h1>
          <p>质检通过后的格式转换、供应商回标、build 入库</p>
        </div>
        <Button size="small" variant="default" onClick={() => reloadCurrent()} disabled={loading}>
          刷新列表
        </Button>
      </div>

      {info && <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 text-sm text-green-700">{info}</div>}
      {error && <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-600">{error}</div>}

      <ExportPipelineFlow pendingExport={pendingExport} pendingBuild={pendingBuild} />

      <LabelingListToolbar
        search={search}
        onSearchChange={setSearch}
        filters={[
          { label: "全部", value: "" },
          { label: "待导出", value: "labeling_submitted" },
          { label: "待入库", value: "returned" },
        ]}
        filterValue={stageFilter}
        onFilterChange={setStageFilter}
        total={total}
      />

      <PageQueryState loading={loading} error={null} empty={!loading && total === 0}>
        {total > 0 ? (
          <>
            <ExportBatchTable
              batches={batches}
              importingId={importingId}
              buildingId={buildingId}
              onExport={handleExport}
              onImportVendor={handleImportVendor}
              onSubmitBuild={handleSubmitBuild}
            />
            <ListPaginationBar
              total={total}
              offset={offset}
              limit={limit}
              onOffsetChange={(o) => load(o, limit)}
              onLimitChange={(l) => load(0, l)}
            />
          </>
        ) : (
          <div className="card text-center py-12">
            <p className="text-gray-400 text-lg mb-3">暂无待导出或待入库的批次</p>
            <p className="text-gray-400 text-sm mb-4">完成标注并质检通过后，批次会出现在此处</p>
            <Link to="/labeling/campaigns"><Button variant="default" size="small">去标注进度 →</Button></Link>
          </div>
        )}
      </PageQueryState>
    </div>
  );
};
