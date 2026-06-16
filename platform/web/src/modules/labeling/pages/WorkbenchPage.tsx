import React, { useEffect, useState, useCallback } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import { LabelingListToolbar } from "../components/LabelingListToolbar";
import { WorkbenchBatchTable } from "../components/WorkbenchBatchTable";
import { displayTaskFields } from "@/lib/labelingDisplay";
import type { LabelingBatchRow } from "@/lib/types";

export const WorkbenchPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [indexedAt, setIndexedAt] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [stage, setStage] = useState("raw_pool");
  const [search, setSearch] = useState("");

  const STAGE_FILTERS = [
    { label: "待送标", value: "raw_pool" },
    { label: "标中", value: "out_for_labeling" },
    { label: "待入库", value: "returned" },
  ];

  const load = useCallback(async (filterStage: string, newOffset: number, newLimit: number) => {
    setLoading(true);
    setError(null);
    try {
      const q = search.trim() || undefined;
      const res = await hsapApi.labelingBatches({ stage: filterStage, offset: newOffset, limit: newLimit, q });
      setBatches((res.items || []) as LabelingBatchRow[]);
      setTotal(res.total ?? 0);
      setOffset(newOffset);
      setLimit(newLimit);
      setIndexedAt(res.updated_at || null);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [search]);

  const [archivingId, setArchivingId] = useState<string | null>(null);

  const handleRebuildIndex = async () => {
    setRebuilding(true);
    setError(null);
    try {
      const r = await hsapApi.rebuildBatchIndex();
      setInfo(`索引已更新 ${r.count} 条（${r.elapsed_ms}ms）`);
      await load(stage, offset, limit);
    } catch (e) {
      setError(String(e));
    }
    setRebuilding(false);
  };

  useEffect(() => { void load(stage, 0, limit); }, [stage, search]);

  const handleOpenCampaign = async (row: LabelingBatchRow) => {
    if (!row.task) return;
    try {
      await hsapApi.openLabelingCampaign({
        project: row.project, task: row.task, batch: row.batch,
        mode: row.mode || null, pack: row.pack || null, location: row.location,
      });
      load(stage, offset, limit);
    } catch (e) { setError(String(e)); }
  };

  const handleArchive = async (row: LabelingBatchRow) => {
    const cid = row.campaign_id;
    if (!cid) return;
    const label = `${displayTaskFields(row)} / ${row.batch}`;
    const ok = window.confirm(
      `确定从工作台移除「${label}」？\n\n`
      + "不会删除磁盘上的图片与标注文件，仅从列表隐藏。\n"
      + "之后可在批次台账重新扫描登记。",
    );
    if (!ok) return;
    setArchivingId(cid);
    setError(null);
    try {
      await hsapApi.archiveLabelingBatch(cid);
      setInfo(`已移除: ${row.batch}`);
      await load(stage, offset, limit);
    } catch (e) {
      setError(String(e));
    }
    setArchivingId(null);
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>送标工作台</h1>
          <p>管理数据标注批次的全生命周期</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="default" size="small" onClick={handleRebuildIndex} loading={rebuilding}>
            同步磁盘
          </Button>
          {indexedAt && <span className="text-xs text-gray-400">索引 {indexedAt.slice(11, 19)}</span>}
        </div>
      </div>

      {info && <div className="bg-green-50 border border-green-200 rounded p-3 mb-4 text-sm text-green-700">{info}</div>}

      <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-2 mb-4 text-xs text-blue-800">
        新批次请先在 <a href="/labeling/deliveries" className="underline font-medium">批次台账</a> 扫描数据湖或登记 NAS 送标，入湖后再来此开标。
      </div>

      <LabelingListToolbar
        search={search}
        onSearchChange={setSearch}
        placeholder="搜索批次/任务..."
        filters={STAGE_FILTERS}
        filterValue={stage}
        onFilterChange={setStage}
        total={total}
      />

      <PageQueryState loading={loading} error={error} empty={!loading && total === 0}>
        {total > 0 && (
          <>
            <WorkbenchBatchTable
              batches={batches}
              onOpenCampaign={handleOpenCampaign}
              onArchive={handleArchive}
              archivingId={archivingId}
            />
            <ListPaginationBar
              total={total}
              offset={offset}
              limit={limit}
              onOffsetChange={(o) => load(stage, o, limit)}
              onLimitChange={(l) => load(stage, 0, l)}
            />
          </>
        )}
      </PageQueryState>
    </div>
  );
};
// FORCE REBUILD 1780387552
// UNIQUE_MARKER_1780387674745592125
// CARD_LAYOUT_MARKER_v2_20260602
