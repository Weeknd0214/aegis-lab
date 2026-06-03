import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import { useAuth } from "@/app/AuthContext";

type RejectionCategory = { key: string; label: string };

export const AuditQueuePage: React.FC = () => {
  const { hasPermission: can } = useAuth();
  const isReviewer = can("write:approval_review") || can("*");
  const [approvals, setApprovals] = useState<Record<string, unknown>[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchMode, setBatchMode] = useState<"" | "approve" | "reject">("");
  const [rejectCategory, setRejectCategory] = useState("");
  const [rejectComment, setRejectComment] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [categories, setCategories] = useState<RejectionCategory[]>([]);
  const [search, setSearch] = useState("");

  const load = useCallback(async (newOffset = 0, newLimit = 20) => {
    setLoading(true); setError(null);
    try {
      const res = await hsapApi.listApprovals({ status: filterStatus || undefined, offset: newOffset, limit: newLimit });
      let items = (res.items || []) as Record<string, unknown>[];
      if (search) {
        const q = search.toLowerCase();
        items = items.filter((a) =>
          String(a.action_label || a.action || "").toLowerCase().includes(q) ||
          String(a.submitted_by || "").toLowerCase().includes(q)
        );
      }
      setApprovals(items);
      setTotal(search ? items.length : res.total);
      setOffset(newOffset); setLimit(newLimit);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, [filterStatus]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (isReviewer) { hsapApi.approvalRejectionCategories().then((r) => setCategories(r.categories || [])); }
  }, [isReviewer]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const toggleAll = () => {
    if (selected.size === approvals.length) { setSelected(new Set()); }
    else { setSelected(new Set(approvals.filter((a) => a.status === "pending").map((a) => a.id as string))); }
  };

  const handleBatchAction = async () => {
    if (selected.size === 0) return;
    setBatchBusy(true);
    const ids = [...selected];
    try {
      if (batchMode === "approve") {
        await hsapApi.batchApprove(ids);
      } else if (batchMode === "reject") {
        await hsapApi.batchReject(ids, rejectComment || undefined, rejectCategory || undefined);
      }
      setSelected(new Set());
      setBatchMode("");
      load(offset, limit);
    } catch (e) { setError(String(e)); }
    setBatchBusy(false);
  };

  const handleSingleApprove = async (id: string) => {
    try { await hsapApi.approve(id); load(offset, limit); }
    catch (e) { setError(String(e)); }
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>审核队列</h1>
          <p>审核平台中所有操作请求</p>
        </div>
        <Button size="small" variant="default" onClick={() => load(offset, limit)}>刷新</Button>
      </div>

      {/* Filter + Batch bar */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <input className="form-input w-44" placeholder="搜索操作/提单人..." value={search} onChange={(e) => { setSearch(e.target.value); }} />
        <select className="form-input w-auto" value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setSelected(new Set()); }}>
          <option value="">全部</option>
          <option value="pending">待审核</option>
          <option value="approved">已通过</option>
          <option value="rejected">已驳回</option>
        </select>
        {isReviewer && selected.size > 0 && (
          <>
            <span className="text-sm text-gray-500">{selected.size} 项已选</span>
            {!batchMode ? (
              <>
                <Button size="small" variant="success" onClick={() => setBatchMode("approve")}>批量通过</Button>
                <Button size="small" variant="danger" onClick={() => setBatchMode("reject")}>批量驳回</Button>
              </>
            ) : (
              <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                <span className="text-sm font-medium">{batchMode === "approve" ? "批量通过" : "批量驳回"}</span>
                {batchMode === "reject" && (
                  <>
                    <select className="form-input w-auto text-xs" value={rejectCategory} onChange={(e) => setRejectCategory(e.target.value)}>
                      <option value="">选择原因</option>
                      {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </select>
                    <input className="form-input w-40 text-xs" value={rejectComment} onChange={(e) => setRejectComment(e.target.value)} placeholder="备注（可选）" />
                  </>
                )}
                <Button size="small" variant={batchMode === "approve" ? "success" : "danger"} onClick={handleBatchAction} loading={batchBusy}>确认</Button>
                <Button size="small" variant="default" onClick={() => { setBatchMode(""); setRejectCategory(""); setRejectComment(""); }}>取消</Button>
              </div>
            )}
          </>
        )}
      </div>

      <PageQueryState loading={loading} error={error} empty={approvals.length === 0} emptyMessage="暂无审核记录">
        <div className="card overflow-hidden">
          <table className="table-auto">
            <thead>
              <tr>
                {isReviewer && <th className="w-8"><input type="checkbox" onChange={toggleAll} checked={selected.size > 0 && selected.size === approvals.filter((a) => a.status === "pending").length} /></th>}
                <th>操作</th>
                <th>状态</th>
                <th>详情</th>
                <th>提单人</th>
                <th>审核人</th>
                <th>驳回原因</th>
                <th>时间</th>
                {isReviewer && <th>操作</th>}
              </tr>
            </thead>
            <tbody>
              {approvals.map((a) => {
                const params = a.params as Record<string, unknown> | undefined;
                const detail = params
                  ? Object.entries(params).filter(([k]) => !["project", "submitted_by"].includes(k)).map(([k, v]) => `${k}=${v}`).join(", ")
                  : "";
                return (
                  <tr key={a.id as string} className={a.status === "pending" && selected.has(a.id as string) ? "bg-blue-50" : ""}>
                    {isReviewer && (
                      <td>
                        {a.status === "pending" && (
                          <input type="checkbox" checked={selected.has(a.id as string)} onChange={() => toggleSelect(a.id as string)} />
                        )}
                      </td>
                    )}
                    <td>
                      <Link to={`/system/audit/${a.id}`} className="text-blue-600 hover:underline text-sm font-medium">
                        {a.action_label as string || a.action as string || "—"}
                      </Link>
                    </td>
                    <td><StatusBadge status={(a.status as string) || "pending"} /></td>
                    <td className="text-xs text-gray-500 max-w-xs truncate">{detail || "—"}</td>
                    <td>{a.submitted_by as string || "—"}</td>
                    <td>{a.reviewed_by as string || "—"}</td>
                    <td className="text-xs">
                      {a.status === "rejected" && a.rejection_category ? (
                        <Badge variant="danger" size="small">{a.rejection_category as string}</Badge>
                      ) : a.status === "rejected" ? (
                        <span className="text-gray-400">—</span>
                      ) : null}
                    </td>
                    <td className="text-xs text-gray-500 whitespace-nowrap">{a.submitted_at as string || a.created_at as string || "—"}</td>
                    {isReviewer && (
                      <td>
                        {a.status === "pending" && (
                          <div className="flex gap-1">
                            <Button size="small" variant="success" onClick={() => handleSingleApprove(a.id as string)}>通过</Button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <ListPaginationBar total={total} offset={offset} limit={limit}
            onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
        </div>
      </PageQueryState>
    </div>
  );
};
