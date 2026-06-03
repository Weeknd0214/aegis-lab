import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import type { BatchDelivery } from "@/lib/types";
import { useAuth } from "@/app/AuthContext";

export const DeliveriesPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [deliveries, setDeliveries] = useState<BatchDelivery[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = async (newOffset = 0, newLimit = 20) => {
    setLoading(true); setError(null);
    try {
      const res = await hsapApi.listDeliveries({ status: statusFilter || undefined, offset: newOffset, limit: newLimit });
      let items = res.items || [];
      if (search) {
        const q = search.toLowerCase();
        items = items.filter((d) => (d.batch_name || "").toLowerCase().includes(q) || (d.task || "").toLowerCase().includes(q) || (d.owner_name || "").toLowerCase().includes(q));
      }
      setDeliveries(items);
      setTotal(search ? items.length : res.total);
      setOffset(newOffset); setLimit(newLimit);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [search, statusFilter]);

  const handleCreate = async () => {
    const batchName = prompt("批次名称 (如 20260601_pilot):");
    if (!batchName) return;
    const dataPath = prompt("数据路径 (如 datasets/dms/inbox/ddaw/20260601_pilot):");
    if (!dataPath) return;
    try {
      await hsapApi.createDelivery({
        project: "dms",
        batch_name: batchName,
        data_path: dataPath,
      });
      load(0, limit);
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSubmit = async (id: string) => {
    try {
      await hsapApi.submitDelivery(id);
      load(offset, limit);
    } catch (e) {
      setError(String(e));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此送标记录？")) return;
    try {
      await hsapApi.deleteDelivery(id);
      load(offset, limit);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>批次台账</h1>
          <p>管理数据送标申请与审核流程</p>
        </div>
        {hasPermission("write:delivery_submit") && (
          <Button variant="primary" onClick={handleCreate}>新建送标</Button>
        )}
      </div>

      {/* Search & Filter */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-[200px] relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="搜索批次/任务/提单人..." value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
          </div>
          <div className="flex gap-1.5">
            {["全部", "草稿", "已提交", "已入湖", "已驳回"].map((label, i) => {
              const val = i === 0 ? "" : ["draft", "submitted", "ingested", "rejected"][i - 1];
              return <button key={val} onClick={() => { setStatusFilter(val); setOffset(0); }} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${statusFilter === val ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>{label}</button>;
            })}
          </div>
          <Button size="small" variant="default" onClick={() => load(0, limit)}>刷新</Button>
          <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">{total} 条</span>
        </div>
      </div>

      <PageQueryState loading={loading} error={error} empty={deliveries.length === 0} emptyMessage="暂无送标记录">
        <div className="space-y-2">
          {deliveries.map((d) => (
            <div key={d.id} className="card hover:shadow-sm transition-shadow">
              <div className="flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{d.batch_name}</span>
                    <span className="text-xs text-gray-400">{d.project}/{d.task || "—"}</span>
                    <StatusBadge status={d.status} />
                  </div>
                  <div className="flex gap-3 mt-1 text-xs text-gray-400">
                    <span>🖼 {d.estimated_count ?? "—"}</span>
                    <span>👤 {d.submitted_by_name || d.owner_name || "—"}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {d.status === "draft" && (
                    <>
                      <button onClick={() => handleSubmit(d.id)} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors">✅ 提交审核</button>
                      <button onClick={() => handleDelete(d.id)} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors">🗑 删除</button>
                    </>
                  )}
                  {d.approval_id && (
                    <Link to={`/system/audit/${d.approval_id}`} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-50 text-gray-600 hover:bg-gray-100 transition-colors">📋 审核</Link>
                  )}
                  {d.status === "ingested" && <span className="text-green-600 text-sm font-medium">✓ 已入湖</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
        <ListPaginationBar total={total} offset={offset} limit={limit} onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
      </PageQueryState>
    </div>
  );
};
