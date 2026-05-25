import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api, type ApprovalRecord, type AuditImageItem, type AuditPreview } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";

const STATUS: Record<string, { label: string; badge: string }> = {
  pending: { label: "待审核", badge: "badge-pending" },
  approved: { label: "已通过", badge: "badge-staged" },
  rejected: { label: "已驳回", badge: "badge-idle" },
  executed: { label: "已执行", badge: "badge-evaluated" },
  failed: { label: "执行失败", badge: "badge-pending" },
  running: { label: "执行中", badge: "badge-training" },
};

type Ctx = { refreshMeta: () => void };

function AuthImage({
  approvalId,
  imageId,
  thumb = true,
  alt,
  className,
  onClick,
}: {
  approvalId: string;
  imageId: string;
  thumb?: boolean;
  alt: string;
  className?: string;
  onClick?: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    setFailed(false);
    setSrc(null);

    api.fetchApprovalImageBlob(approvalId, imageId, thumb).then(
      (url) => {
        if (revoked) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setSrc(url);
      },
      () => {
        if (!revoked) setFailed(true);
      }
    );

    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [approvalId, imageId, thumb]);

  if (failed) {
    return <div className={`audit-img-placeholder ${className || ""}`}>加载失败</div>;
  }
  if (!src) {
    return <div className={`audit-img-placeholder audit-img-loading ${className || ""}`}>…</div>;
  }
  return <img src={src} alt={alt} className={className} onClick={onClick} loading="lazy" />;
}

export function AuditDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { refreshMeta } = useOutletContext<Ctx>();
  const toast = useToast();
  const { hasPermission } = useAuth();
  const canReview = hasPermission("write:approval_review");

  const [preview, setPreview] = useState<AuditPreview | null>(null);
  const [images, setImages] = useState<AuditImageItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [lightbox, setLightbox] = useState<AuditImageItem | null>(null);
  const [batchFilter, setBatchFilter] = useState("");
  const sentinelRef = useRef<HTMLDivElement>(null);

  const approvalId = id || "";

  const loadPreview = useCallback(async () => {
    if (!approvalId) return;
    const data = await api.getApprovalPreview(approvalId);
    setPreview(data);
  }, [approvalId]);

  const loadImages = useCallback(
    async (append = false) => {
      if (!approvalId) return;
      if (append) setLoadingMore(true);
      else setLoading(true);
      try {
        const offset = append ? images.length : 0;
        const data = await api.listApprovalImages(approvalId, offset, 60);
        setTotal(data.total);
        setImages((prev) => (append ? [...prev, ...data.items] : data.items));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [approvalId, images.length]
  );

  useEffect(() => {
    loadPreview().catch((e) => toast(String(e), true));
    loadImages(false).catch((e) => toast(String(e), true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approvalId]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || loading || loadingMore || images.length >= total) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && images.length < total) {
          loadImages(true).catch((e) => toast(String(e), true));
        }
      },
      { rootMargin: "200px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [images.length, total, loading, loadingMore, loadImages, toast]);

  const rec: ApprovalRecord | undefined = preview?.approval;
  const st = rec ? STATUS[rec.status] || { label: rec.status, badge: "badge-idle" } : null;
  const batches = [...new Set(images.map((i) => i.batch))].sort();
  const shown = batchFilter ? images.filter((i) => i.batch === batchFilter) : images;

  return (
    <>
      <div className="audit-detail-head panel panel-compact">
        <div className="panel-body">
          <div className="audit-detail-nav">
            <Link to="/audit" className="btn btn-sm btn-ghost">← 返回队列</Link>
            {rec && st && (
              <span className={`badge ${st.badge}`}>{st.label}</span>
            )}
          </div>
          {rec && (
            <>
              <h2 className="audit-detail-title">{rec.action_label || rec.action}</h2>
              <p className="text-dim audit-detail-meta">
                {rec.id} · {rec.submitted_by || "—"} · {rec.submitted_at?.slice(0, 19)}
              </p>
              {preview?.scope_label && (
                <p className="audit-scope-label">{preview.scope_label}</p>
              )}
              {preview?.batches?.length ? (
                <div className="audit-batch-tags">
                  {preview.batches.map((b) => (
                    <span key={`${b.location}:${b.batch}`} className={`audit-batch-tag ${b.exists ? "" : "missing"}`}>
                      {b.location}/{b.batch}
                      {!b.exists && " (目录不存在)"}
                    </span>
                  ))}
                </div>
              ) : null}
              {rec.status === "pending" && canReview && (
                <div className="audit-detail-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={async () => {
                      try {
                        await api.approve(rec.id, "批准");
                        toast("已批准");
                        refreshMeta();
                        loadPreview();
                      } catch (e) {
                        toast(String(e), true);
                      }
                    }}
                  >
                    批准执行
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={async () => {
                      const reason = prompt("驳回原因");
                      if (reason === null) return;
                      await api.reject(rec.id, reason);
                      toast("已驳回");
                      refreshMeta();
                      loadPreview();
                    }}
                  >
                    驳回
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>送标注图 · GT 可视化</h2>
          <div className="audit-gallery-toolbar">
            <span className="text-dim">
              已加载 {images.length} / {total} 张
            </span>
            {batches.length > 1 && (
              <select
                className="audit-batch-select"
                value={batchFilter}
                onChange={(e) => setBatchFilter(e.target.value)}
              >
                <option value="">全部批次</option>
                {batches.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className="panel-body">
          {loading && !images.length ? (
            <p className="empty-state">加载图像…</p>
          ) : total === 0 ? (
            <p className="empty-state">该审核单范围内未找到送标注图像</p>
          ) : (
            <>
              <div className="audit-gallery">
                {shown.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`audit-gallery-item ${item.missing_label ? "no-label" : ""}`}
                    onClick={() => setLightbox(item)}
                    title={item.filename}
                  >
                    <AuthImage
                      approvalId={approvalId}
                      imageId={item.id}
                      thumb
                      alt={item.filename}
                      className="audit-gallery-img"
                    />
                    <div className="audit-gallery-cap">
                      <span className="mono">{item.filename}</span>
                      <span>
                        {item.batch} · {item.split}
                        {item.box_count > 0 ? ` · ${item.box_count} 框` : item.missing_label ? " · 无标注" : ""}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
              {loadingMore && <p className="empty-state">加载更多…</p>}
              <div ref={sentinelRef} className="audit-sentinel" />
            </>
          )}
        </div>
      </div>

      {lightbox && (
        <div className="audit-lightbox" onClick={() => setLightbox(null)} role="presentation">
          <div className="audit-lightbox-inner" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="audit-lightbox-close btn btn-sm btn-ghost" onClick={() => setLightbox(null)}>
              关闭
            </button>
            <AuthImage
              approvalId={approvalId}
              imageId={lightbox.id}
              thumb={false}
              alt={lightbox.filename}
              className="audit-lightbox-img"
            />
            <div className="audit-lightbox-meta">
              <strong>{lightbox.filename}</strong>
              <span>{lightbox.batch} · {lightbox.split} · {lightbox.box_count} 个标注框</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function AuditPage() {
  const navigate = useNavigate();
  const { refreshMeta } = useOutletContext<Ctx>();
  const toast = useToast();
  const { hasPermission } = useAuth();
  const canReview = hasPermission("write:approval_review");
  const [filter, setFilter] = useState("pending");
  const [items, setItems] = useState<ApprovalRecord[]>([]);

  const load = async () => {
    const data = await api.listApprovals(filter || undefined);
    setItems(data.items || []);
  };

  useEffect(() => { load(); }, [filter]);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>审核队列</h2>
        <div className="audit-filters">
          {["pending", "executed", "rejected", "failed", ""].map((f) => (
            <button key={f || "all"} type="button" className={`btn btn-sm ${filter === f ? "btn-primary" : "btn-ghost"}`} onClick={() => setFilter(f)}>
              {f === "" ? "全部" : STATUS[f]?.label || f}
            </button>
          ))}
        </div>
      </div>
      <div className="panel-body table-wrap">
        <table className="data-table audit-table">
          <thead><tr><th>单号</th><th>动作</th><th>状态</th><th>提交人</th><th>时间</th><th>参数</th><th>操作</th></tr></thead>
          <tbody>
            {items.map((r) => {
              const st = STATUS[r.status] || { label: r.status, badge: "badge-idle" };
              return (
                <tr
                  key={r.id}
                  className="audit-row-clickable"
                  onClick={() => navigate(`/audit/${r.id}`)}
                >
                  <td className="mono text-sm">{r.id}</td>
                  <td>{r.action_label || r.action}</td>
                  <td><span className={`badge ${st.badge}`}>{st.label}</span></td>
                  <td>{r.submitted_by || "—"}</td>
                  <td className="text-sm">{r.submitted_at?.slice(0, 19)}</td>
                  <td className="text-sm"><pre className="params-pre">{JSON.stringify(r.params || {})}</pre></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => navigate(`/audit/${r.id}`)}>
                      查看标注图
                    </button>
                    {r.status === "pending" && canReview ? (
                      <>
                        <button type="button" className="btn btn-sm btn-primary" onClick={async () => {
                          try { await api.approve(r.id, "批准"); toast("已批准"); load(); refreshMeta(); }
                          catch (e) { toast(String(e), true); }
                        }}>批准</button>
                        <button type="button" className="btn btn-sm btn-ghost" onClick={async () => {
                          await api.reject(r.id, prompt("驳回原因") || "");
                          load(); refreshMeta();
                        }}>驳回</button>
                      </>
                    ) : r.status === "pending" ? (
                      <span className="text-dim">无审核权限</span>
                    ) : (
                      r.review_comment || r.result?.error || ""
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
