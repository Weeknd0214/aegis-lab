import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import { CompactTableShell } from "@/components/CompactTableShell";
import { LabelingListToolbar } from "../components/LabelingListToolbar";
import { DeliveryTable } from "../components/DeliveryTable";
import { DeliveryCreateModal, type DeliveryFormValues } from "../components/DeliveryCreateModal";
import { DeliveryIntakePanel } from "../components/DeliveryIntakePanel";
import { displayTaskFields } from "@/lib/labelingDisplay";
import type { BatchDelivery } from "@/lib/types";
import { useAuth } from "@/app/AuthContext";

type ScanItem = {
  project: string;
  task: string;
  batch_name: string;
  images: number;
  labels: number;
  stage_hint: string;
  in_ledger: boolean;
  in_workbench: boolean;
  needs_ledger: boolean;
  delivery_status?: string;
  collection_start?: string;
  data_path: string;
};

const STATUS_FILTERS = [
  { label: "全部", value: "" },
  { label: "草稿", value: "draft" },
  { label: "待审核", value: "pending_review" },
  { label: "已入湖", value: "in_lake" },
  { label: "入湖失败", value: "ingest_failed" },
  { label: "已驳回", value: "rejected" },
];

function parseApiError(e: unknown): string {
  const raw = String(e);
  try {
    const m = raw.match(/\{.*\}/s);
    if (m) {
      const j = JSON.parse(m[0]) as { detail?: string };
      if (j.detail) return j.detail;
    }
  } catch { /* ignore */ }
  return raw;
}

export const DeliveriesPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const canSubmit = hasPermission("write:delivery_submit");

  const [deliveries, setDeliveries] = useState<BatchDelivery[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [scanning, setScanning] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showScan, setShowScan] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [scanItems, setScanItems] = useState<ScanItem[]>([]);
  const [scanMeta, setScanMeta] = useState<{ needs_ledger: number; needs_workbench: number; scanned_at?: string } | null>(null);

  const load = async (newOffset = 0, newLimit = 20) => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.listDeliveries({ status: statusFilter || undefined, offset: newOffset, limit: newLimit });
      let items = res.items || [];
      if (search) {
        const q = search.toLowerCase();
        items = items.filter((d) =>
          (d.batch_name || "").toLowerCase().includes(q)
          || (d.task || "").toLowerCase().includes(q)
          || (d.owner_name || "").toLowerCase().includes(q),
        );
      }
      setDeliveries(items);
      setTotal(search ? items.length : res.total);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [search, statusFilter]);

  const stats = useMemo(() => {
    const inLake = deliveries.filter((d) => d.status === "in_lake").length;
    const pending = deliveries.filter((d) => ["draft", "pending_review", "ingesting", "ingest_failed", "rejected"].includes(d.status)).length;
    return { inLake, pending };
  }, [deliveries]);

  const handleScan = async () => {
    setScanning(true);
    setActionError(null);
    try {
      const res = await hsapApi.scanDeliveries();
      const items = (res.items || []) as unknown as ScanItem[];
      setScanItems(items);
      setScanMeta({
        needs_ledger: res.needs_ledger ?? 0,
        needs_workbench: res.needs_workbench ?? 0,
        scanned_at: res.scanned_at,
      });
      setShowScan(true);
    } catch (e) {
      setActionError(parseApiError(e));
    }
    setScanning(false);
  };

  const handleRegisterAll = async () => {
    const pending = scanItems.filter((i) => i.needs_ledger);
    if (pending.length === 0) {
      setInfo("所有 inbox 批次均已登记到台账");
      return;
    }
    if (!confirm(
      `将 ${pending.length} 个未登记批次写入台账，并同步到送标工作台？\n\n`
      + "已在 inbox 的批次将直接标为「已入湖」，采集时间取目录修改日期。",
    )) return;
    setRegistering(true);
    setActionError(null);
    try {
      const r = await hsapApi.registerScannedDeliveries(
        pending as unknown as Record<string, unknown>[],
        true,
      );
      setInfo(`台账新增 ${r.created} 条，更新 ${r.updated} 条，工作台同步 ${r.synced_workbench} 条`);
      setShowScan(false);
      await load(0, limit);
    } catch (e) {
      setActionError(parseApiError(e));
    }
    setRegistering(false);
  };

  const handleCreateSubmit = async (values: DeliveryFormValues) => {
    setSaving(true);
    setActionError(null);
    try {
      await hsapApi.createDelivery({
        project: values.project,
        task: values.project === "lane" ? values.task || "lane_v1" : values.task.trim() || null,
        mode: values.mode.trim() || null,
        batch_name: values.batch_name.trim(),
        data_path: values.data_path.trim(),
        source_type: values.source_type,
        collection_start: values.collection_start || null,
        collection_end: values.collection_end || null,
        estimated_count: values.estimated_count ? Number(values.estimated_count) : null,
        vehicle_scene: values.vehicle_scene.trim() || null,
        remark: values.remark.trim() || null,
      });
      setShowCreate(false);
      await load(0, limit);
      setInfo("已保存草稿。请核对后点「提交」走审批入湖。");
    } catch (e) {
      setActionError(parseApiError(e));
    }
    setSaving(false);
  };

  const handleSubmit = async (id: string) => {
    setActionError(null);
    try {
      await hsapApi.submitDelivery(id);
      await load(offset, limit);
      setInfo("已提交审批，请在审核管理批准入湖");
    } catch (e) {
      setActionError(parseApiError(e));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此送标记录？")) return;
    setActionError(null);
    try {
      await hsapApi.deleteDelivery(id);
      await load(offset, limit);
    } catch (e) {
      setActionError(parseApiError(e));
    }
  };

  const pendingScan = scanItems.filter((i) => i.needs_ledger);

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between gap-4">
        <div>
          <h1>批次台账</h1>
          <p>数据湖周期落盘 · NAS 外挂盘 · 统一登记采集周期 → 入湖 → 工作台开标</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="primary" size="small" onClick={handleScan} loading={scanning}>
            扫描数据湖
          </Button>
          {canSubmit && (
            <Button variant="default" size="small" onClick={() => setShowCreate(true)}>
              新建送标
            </Button>
          )}
        </div>
      </div>

      <DeliveryIntakePanel
        total={total}
        inLake={stats.inLake}
        pending={stats.pending}
        scanPending={scanMeta?.needs_ledger}
        scanning={scanning}
        canCreate={canSubmit}
        onScan={handleScan}
        onCreate={() => setShowCreate(true)}
      />

      {info && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 text-sm text-green-700">
          {info}
        </div>
      )}

      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {showScan && (
        <div className="card mb-4 border-blue-200 bg-blue-50/30">
          <div className="card-header flex items-center justify-between gap-2">
            <span>
              数据湖扫描 — 共 {scanItems.length} 批
              {scanMeta && (
                <span className="text-gray-500 text-sm ml-2">
                  未登记台账 {scanMeta.needs_ledger} · 未进工作台 {scanMeta.needs_workbench}
                  {scanMeta.scanned_at && ` · ${scanMeta.scanned_at.slice(11, 19)}`}
                </span>
              )}
            </span>
            <div className="flex gap-2 shrink-0">
              {pendingScan.length > 0 && canSubmit && (
                <Button size="small" variant="primary" loading={registering} onClick={handleRegisterAll}>
                  登记到台账 ({pendingScan.length})
                </Button>
              )}
              <Button size="small" variant="default" onClick={() => setShowScan(false)}>收起</Button>
            </div>
          </div>
          {scanItems.length === 0 ? (
            <p className="text-sm text-gray-400 p-4">inbox 暂无批次目录</p>
          ) : (
            <CompactTableShell colWidths={["10%", "24%", "10%", "8%", "8%", "10%", "10%", "10%"]}>
              <thead>
                <tr>
                  <th className="py-2">项目</th>
                  <th className="py-2">批次</th>
                  <th className="py-2">任务</th>
                  <th className="py-2">图片</th>
                  <th className="py-2">采集</th>
                  <th className="py-2">台账</th>
                  <th className="py-2">工作台</th>
                  <th className="py-2">阶段</th>
                </tr>
              </thead>
              <tbody>
                {scanItems.slice(0, 50).map((item) => (
                  <tr key={`${item.project}/${item.task}/${item.batch_name}`} className="align-middle">
                    <td className="py-2 text-xs uppercase text-gray-600">{item.project}</td>
                    <td className="py-2 text-sm font-medium truncate max-w-[12rem]" title={item.batch_name}>{item.batch_name}</td>
                    <td className="py-2 text-sm">{displayTaskFields(item)}</td>
                    <td className="py-2 text-sm tabular-nums">{item.images}</td>
                    <td className="py-2 text-xs text-gray-500">{item.collection_start?.slice(0, 10) || "—"}</td>
                    <td className="py-2">
                      {item.in_ledger
                        ? <Badge variant="success" size="small">已登记</Badge>
                        : <Badge variant="warning" size="small">待登记</Badge>}
                    </td>
                    <td className="py-2">
                      {item.in_workbench
                        ? <Badge variant="success" size="small">已同步</Badge>
                        : <Badge variant="default" size="small">未同步</Badge>}
                    </td>
                    <td className="py-2 text-xs text-gray-500">{item.stage_hint === "returned" ? "待入库" : "待送标"}</td>
                  </tr>
                ))}
              </tbody>
            </CompactTableShell>
          )}
          {scanItems.length > 50 && (
            <p className="text-xs text-gray-400 p-2">仅展示前 50 条，登记时会处理全部未登记批次</p>
          )}
        </div>
      )}

      <LabelingListToolbar
        search={search}
        onSearchChange={(v) => { setSearch(v); setOffset(0); }}
        placeholder="搜索批次/任务/提单人..."
        filters={STATUS_FILTERS}
        filterValue={statusFilter}
        onFilterChange={(v) => { setStatusFilter(v); setOffset(0); }}
        total={total}
        extra={<Button size="small" variant="default" onClick={() => load(0, limit)}>刷新</Button>}
      />

      <PageQueryState loading={loading} error={error} empty={false}>
        {!loading && deliveries.length === 0 ? (
          <div className="card py-16 text-center">
            <div className="text-4xl mb-3">📋</div>
            <p className="text-gray-600 font-medium mb-1">暂无送标记录</p>
            <p className="text-sm text-gray-400 mb-6 max-w-md mx-auto">
              数据湖 inbox 已有批次？先点「扫描数据湖」批量登记。
              NAS 外挂盘新数据？点「新建送标」填写路径与采集周期。
            </p>
            <div className="flex justify-center gap-3">
              <Button variant="primary" onClick={handleScan} loading={scanning}>扫描数据湖</Button>
              {canSubmit && <Button variant="default" onClick={() => setShowCreate(true)}>新建送标</Button>}
            </div>
          </div>
        ) : (
          <>
            <DeliveryTable
              deliveries={deliveries}
              canSubmit={canSubmit}
              onSubmit={handleSubmit}
              onDelete={handleDelete}
            />
            <ListPaginationBar
              total={total}
              offset={offset}
              limit={limit}
              onOffsetChange={(o) => load(o, limit)}
              onLimitChange={(l) => load(0, l)}
            />
          </>
        )}
      </PageQueryState>

      <DeliveryCreateModal
        open={showCreate}
        saving={saving}
        onClose={() => setShowCreate(false)}
        onSubmit={handleCreateSubmit}
      />
    </div>
  );
};
