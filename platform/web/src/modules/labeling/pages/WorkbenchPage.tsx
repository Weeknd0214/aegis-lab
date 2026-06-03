import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StageBadge, Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import type { LabelingBatchRow } from "@/lib/types";

type ScanItem = { project: string; task: string; batch: string; path: string; images: number; labels: number; has_labels: boolean; stage_hint: string };

export const WorkbenchPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [stage, setStage] = useState("raw_pool");
  const [search, setSearch] = useState("");

  const filteredBatches = batches.filter((b) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (b.batch || "").toLowerCase().includes(q) || (b.task || "").toLowerCase().includes(q);
  });

  // Scan inbox
  const [scanning, setScanning] = useState(false);
  const [scanItems, setScanItems] = useState<ScanItem[]>([]);
  const [showScan, setShowScan] = useState(false);
  const [registering, setRegistering] = useState<string | null>(null);

  const load = useCallback(async (filterStage: string) => {
    setLoading(true); setError(null);
    try {
      const res = await hsapApi.labelingBatches({ stage: filterStage, limit: 100 });
      setBatches((res.items || []) as LabelingBatchRow[]);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(stage); }, [stage, load]);

  const handleScan = async () => {
    setScanning(true); setError(null);
    try {
      const dms = await hsapApi.scanInbox("dms");
      setScanItems((dms.items || []) as unknown as ScanItem[]);
      setShowScan(true);
    } catch (e) { setError(String(e)); }
    setScanning(false);
  };

  const handleRegister = async (item: ScanItem) => {
    setRegistering(item.batch);
    try {
      await hsapApi.registerBatch({
        project: item.project, task: item.task, batch: item.batch,
        stage: item.stage_hint, location: "inbox",
      });
      setScanItems((prev) => prev.filter((s) => s.batch !== item.batch));
      load(stage);
      setInfo(`已登记: ${item.task}/${item.batch}`);
    } catch (e) { setError(String(e)); }
    setRegistering(null);
  };

  const handleRegisterAll = async () => {
    let count = 0;
    for (const item of scanItems) {
      try {
        await hsapApi.registerBatch({
          project: item.project, task: item.task, batch: item.batch,
          stage: item.stage_hint, location: "inbox",
        });
        count++;
      } catch { /* skip */ }
    }
    setScanItems([]); setShowScan(false);
    load(stage);
    setInfo(`已登记 ${count} 个批次`);
  };

  const handleOpenCampaign = async (row: LabelingBatchRow) => {
    if (!row.task) return;
    try {
      await hsapApi.openLabelingCampaign({
        project: row.project, task: row.task, batch: row.batch,
        mode: row.mode || null, pack: row.pack || null, location: row.location,
      });
      load(stage);
    } catch (e) { setError(String(e)); }
  };

  const STAGES = [
    { key: "raw_pool", label: "待送标" },
    { key: "out_for_labeling", label: "标中" },
    { key: "returned", label: "待入库" },
  ];

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>送标工作台</h1>
          <p>管理数据标注批次的全生命周期</p>
        </div>
        <Button variant="primary" size="small" onClick={handleScan} loading={scanning}>
          扫描入库
        </Button>
      </div>

      {info && <div className="bg-green-50 border border-green-200 rounded p-3 mb-4 text-sm text-green-700">{info}</div>}

      {/* Scan results panel */}
      {showScan && (
        <div className="card mb-4 border-blue-200 bg-blue-50/30">
          <div className="card-header flex items-center justify-between">
            <span>扫描结果 — 发现 {scanItems.length} 个未登记批次</span>
            <div className="flex gap-2">
              {scanItems.length > 0 && <Button size="small" variant="primary" onClick={handleRegisterAll}>全部登记</Button>}
              <Button size="small" variant="default" onClick={() => setShowScan(false)}>收起</Button>
            </div>
          </div>
          {scanItems.length === 0 ? (
            <p className="text-sm text-gray-400">所有 inbox 数据均已登记</p>
          ) : (
            <table className="table-auto">
              <thead>
                <tr><th>任务</th><th>批次</th><th>图片</th><th>标注</th><th>状态</th><th>操作</th></tr>
              </thead>
              <tbody>
                {scanItems.map((item) => (
                  <tr key={`${item.task}/${item.batch}`}>
                    <td className="font-medium">{item.task}</td>
                    <td>{item.batch}</td>
                    <td>{item.images}</td>
                    <td>{item.has_labels ? <Badge variant="success" size="small">{item.labels} 个</Badge> : <span className="text-gray-400">无标注</span>}</td>
                    <td><StageBadge stage={item.stage_hint} /></td>
                    <td>
                      <Button size="small" variant="primary" loading={registering === item.batch} onClick={() => handleRegister(item)}>
                        登记入库
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Stage filter + Search */}
      <div className="flex gap-2 mb-4 items-center flex-wrap">
        {STAGES.map((s) => (
          <button key={s.key} onClick={() => setStage(s.key)}
            className={`px-4 py-2 text-sm rounded-md transition-colors ${stage === s.key ? "bg-blue-700 text-white" : "bg-white border border-gray-300 text-gray-600 hover:bg-gray-50"}`}>
            {s.label}
          </button>
        ))}
        <div className="flex-1" />
        <input className="form-input w-40" placeholder="搜索批次..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <PageQueryState loading={loading} error={error} empty={filteredBatches.length === 0}>
        <div className="space-y-2">
          {filteredBatches.map((b) => (
            <div key={`${b.project}/${b.task}/${b.batch}`} className="card hover:shadow-sm transition-shadow">
              <div className="flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{b.batch}</span>
                    <span className="text-xs text-gray-400">{b.project}/{b.task || "—"}</span>
                    <StageBadge stage={b.stage} />
                  </div>
                  <div className="flex gap-3 mt-1 text-xs text-gray-400">
                    <span>🖼 {b.counts?.images ?? 0}</span>
                    <span>🏷 {b.counts?.labels ?? 0}</span>
                  </div>
                </div>
                <div className="shrink-0">
                  {b.stage === "raw_pool" && (
                    <Button size="small" variant="primary" onClick={() => handleOpenCampaign(b)}>开标</Button>
                  )}
                  {b.stage === "out_for_labeling" && b.campaign_id && (
                    <a href={`/labeling/campaigns/${b.campaign_id}/annotate`} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors">
                      ✏️ 进入标注
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </PageQueryState>
    </div>
  );
};
// FORCE REBUILD 1780387552
// UNIQUE_MARKER_1780387674745592125
// CARD_LAYOUT_MARKER_v2_20260602
