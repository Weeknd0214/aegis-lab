import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { useAuth } from "@/app/AuthContext";

type RejectionCategory = { key: string; label: string };

export const AuditDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { hasPermission: can } = useAuth();
  const isReviewer = can("write:approval_review") || can("*");

  const [approval, setApproval] = useState<Record<string, unknown> | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [images, setImages] = useState<{ id: string; url?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectCategory, setRejectCategory] = useState("");
  const [rejectComment, setRejectComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [categories, setCategories] = useState<RejectionCategory[]>([]);

  const load = async () => {
    if (!id) return;
    setLoading(true); setError(null);
    try {
      const [a, p] = await Promise.all([
        hsapApi.getApproval(id),
        hsapApi.getApprovalPreview(id).catch(() => null),
      ]);
      setApproval(a); setPreview(p as Record<string, unknown> | null);
      const imgRes = await hsapApi.listApprovalImages(id, 0, 60).catch(() => null);
      const items = (imgRes?.items || []) as { id: string }[];
      const withUrls = await Promise.all(items.slice(0, 12).map(async (img) => {
        try { return { ...img, url: await hsapApi.fetchApprovalImageBlob(id, img.id, true) }; }
        catch { return img; }
      }));
      setImages(withUrls);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (isReviewer) { hsapApi.approvalRejectionCategories().then((r) => setCategories(r.categories || [])); }
  }, [isReviewer]);

  const handleApprove = async () => {
    setBusy(true);
    try { await hsapApi.approve(id!); load(); }
    catch (e) { setError(String(e)); }
    setBusy(false);
  };

  const handleReject = async () => {
    setBusy(true);
    try { await hsapApi.reject(id!, rejectComment || undefined, rejectCategory || undefined); load(); setRejecting(false); }
    catch (e) { setError(String(e)); }
    setBusy(false);
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <Link to="/system/audit" className="text-blue-600 text-sm hover:underline mb-2 inline-block">← 返回审核队列</Link>
        <h1>审核详情</h1>
        <p className="font-mono text-xs text-gray-400">ID: {id}</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        {approval && (
          <>
            {/* Summary card */}
            <div className="card mb-4">
              <div className="card-header flex items-center justify-between">
                <span>{approval.action_label as string || approval.action as string || "审核单"}</span>
                <StatusBadge status={(approval.status as string) || "pending"} />
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">提单人: </span><span>{approval.submitted_by as string || "—"}</span>
                </div>
                <div>
                  <span className="text-gray-500">审核人: </span><span>{approval.reviewed_by as string || "—"}</span>
                </div>
                <div>
                  <span className="text-gray-500">提交时间: </span><span className="text-xs">{approval.submitted_at as string || "—"}</span>
                </div>
                <div>
                  <span className="text-gray-500">审核时间: </span><span className="text-xs">{approval.reviewed_at as string || "—"}</span>
                </div>
                {approval.note != null && String(approval.note) && <div className="col-span-2"><span className="text-gray-500">备注: </span>{String(approval.note)}</div>}
                {approval.review_comment != null && String(approval.review_comment) && (
                  <div className="col-span-2">
                    <span className="text-gray-500">审核意见: </span>
                    <span className="text-gray-800">{String(approval.review_comment ?? "")}</span>
                  </div>
                )}
                {approval.rejection_category != null && String(approval.rejection_category) && (
                  <div className="col-span-2">
                    <span className="text-gray-500">驳回分类: </span>
                    <Badge variant="danger">{String(approval.rejection_category ?? "")}</Badge>
                  </div>
                )}
              </div>

              {/* Job link */}
              {approval.job_id != null && String(approval.job_id) && (
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <span className="text-gray-500 text-sm">关联任务: </span>
                  <Link to={`/system/jobs`} className="text-blue-600 text-sm hover:underline font-mono">
                    {String(approval.job_id ?? "")}
                  </Link>
                </div>
              )}
            </div>

            {/* Preview - structured view */}
            {preview && (
              <div className="card mb-4">
                <div className="card-header">变更详情</div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {(preview.task as string) && (
                    <div><span className="text-gray-500">任务: </span><Badge variant="info">{preview.task as string}</Badge></div>
                  )}
                  {(preview.pack as string) && (
                    <div><span className="text-gray-500">数据包: </span><Badge variant="default">{preview.pack as string}</Badge></div>
                  )}
                  {(preview.scope_label as string) && (
                    <div className="col-span-2">
                      <span className="text-gray-500">范围: </span>
                      <span>{String(preview.scope_label ?? "")}</span>
                    </div>
                  )}
                  {(preview.class_names as Record<string, string>) && (
                    <div className="col-span-2">
                      <span className="text-gray-500 text-xs">类别: </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Object.entries(preview.class_names as Record<string, string>).map(([k, v]) => (
                          <Badge key={k} size="small" variant="default">{v || k}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Params detail */}
                {approval.params != null && typeof approval.params === "object" && Object.keys(approval.params as Record<string, unknown>).length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <span className="text-xs text-gray-500 font-semibold">参数明细</span>
                    <pre className="text-xs mt-1 bg-gray-50 p-2 rounded max-h-40 overflow-auto">
                      {JSON.stringify(approval.params, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* Image previews */}
            {images.length > 0 && (
              <div className="card mb-4">
                <div className="card-header">图片预览 ({images.length})</div>
                <div className="flex flex-wrap gap-2">
                  {images.map((img) => (
                    <div key={img.id} className="w-24 h-24 bg-gray-100 rounded overflow-hidden">
                      {img.url ? (
                        <img src={img.url} alt={img.id} className="w-full h-full object-cover" />
                      ) : (
                        <div className="flex items-center justify-center h-full text-gray-400 text-xs">{img.id.slice(0, 8)}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            {approval.status === "pending" && isReviewer && (
              <div className="card">
                {!rejecting ? (
                  <div className="flex gap-2">
                    <Button variant="success" onClick={handleApprove} loading={busy}>✓ 通过</Button>
                    <Button variant="danger" onClick={() => setRejecting(true)}>✗ 驳回</Button>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm font-semibold mb-3">驳回审核</p>
                    <div className="space-y-3">
                      <select className="form-input max-w-xs" value={rejectCategory} onChange={(e) => setRejectCategory(e.target.value)}>
                        <option value="">选择驳回原因分类</option>
                        {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                      </select>
                      <textarea className="form-input max-w-md" value={rejectComment} onChange={(e) => setRejectComment(e.target.value)} placeholder="补充说明（可选）" rows={3} />
                      <div className="flex gap-2">
                        <Button variant="danger" onClick={handleReject} loading={busy} disabled={!rejectCategory}>确认驳回</Button>
                        <Button variant="default" onClick={() => { setRejecting(false); setRejectCategory(""); setRejectComment(""); }}>取消</Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </PageQueryState>
    </div>
  );
};
