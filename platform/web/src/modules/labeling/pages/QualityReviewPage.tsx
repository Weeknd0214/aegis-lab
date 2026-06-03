import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StageBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import type { LabelingBatchRow } from "@/lib/types";

type ReviewItem = { id: string; image_path: string; fileName: string; score: string; has_label: boolean };
type ScoreCounts = { good: number; fine: number; bad: number; pending: number };
type ScoreKey = keyof ScoreCounts;

const SCORE_CFG: Record<ScoreKey, { label: string; color: string; bg: string; icon: string; btn: string }> = {
  good: { label: "合格", color: "text-green-600", bg: "bg-green-500", icon: "✓", btn: "bg-green-600 hover:bg-green-500 text-white" },
  fine: { label: "可用", color: "text-yellow-600", bg: "bg-yellow-500", icon: "~", btn: "bg-yellow-600 hover:bg-yellow-500 text-white" },
  bad: { label: "退回", color: "text-red-600", bg: "bg-red-500", icon: "✗", btn: "bg-red-600 hover:bg-red-500 text-white" },
  pending: { label: "未评", color: "text-gray-400", bg: "bg-gray-300", icon: "○", btn: "" },
};

// ── List ──
const ReviewListPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [filtered, setFiltered] = useState<LabelingBatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [sort, setSort] = useState<"batch"|"task">("batch");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const results: LabelingBatchRow[] = [];
      const [inReview, approved, rejected] = await Promise.allSettled([
        hsapApi.labelingBatches({ stage: "in_review", limit: 100 }),
        hsapApi.labelingBatches({ stage: "review_approved", limit: 50 }),
        hsapApi.labelingBatches({ stage: "review_rejected", limit: 50 }),
      ]);
      if (inReview.status === "fulfilled") results.push(...((inReview.value.items || []) as LabelingBatchRow[]));
      if (approved.status === "fulfilled") results.push(...((approved.value.items || []) as LabelingBatchRow[]));
      if (rejected.status === "fulfilled") results.push(...((rejected.value.items || []) as LabelingBatchRow[]));
      setBatches(results);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let result = [...batches];
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((b) => (b.batch || "").toLowerCase().includes(q) || (b.task || "").toLowerCase().includes(q));
    }
    if (stageFilter) result = result.filter((b) => b.stage === stageFilter);
    result.sort((a, b) => (a[sort] || "").localeCompare(b[sort] || ""));
    setFiltered(result);
  }, [batches, search, stageFilter, sort]);

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>标注质检</h1>
          <p>审核标注质量 — 合格和可用的流入训练集，退回的返回标注员修正</p>
        </div>
        <Button size="small" variant="default" onClick={load}>刷新</Button>
      </div>
      {/* Search & Filter Bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="flex-1 min-w-[200px] relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="搜索批次名称、任务名称..." value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {/* Filter chips */}
          <div className="flex gap-1.5">
            {["全部", "质检中", "已通过", "已退回"].map((label, i) => {
              const val = i === 0 ? "" : ["in_review", "review_approved", "review_rejected"][i - 1];
              return (
                <button key={val} onClick={() => setStageFilter(val)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    stageFilter === val ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  }`}>{label}</button>
              );
            })}
          </div>
          <span className="text-gray-300">|</span>
          {/* Sort */}
          <select className="text-xs border border-gray-300 rounded-lg px-2.5 py-1.5 text-gray-600"
            value={sort} onChange={(e) => setSort(e.target.value as "batch"|"task")}>
            <option value="batch">按批次排序</option>
            <option value="task">按任务排序</option>
          </select>
          {/* Count */}
          <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">{filtered.length} 条</span>
        </div>
      </div>
      <PageQueryState loading={loading} error={error} empty={filtered.length === 0} emptyMessage="暂无待质检的批次">
        <div className="space-y-2">
          {filtered.map((b) => {
            const pct = b.total_tasks && b.total_tasks > 0 ? Math.round(((b.completed_tasks || 0) / b.total_tasks) * 100) : 0;
            return (
              <div key={b.campaign_id || b.batch} className="card hover:shadow-sm transition-shadow">
                <div className="flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm">{b.batch}</span>
                      <span className="text-xs text-gray-400">{b.task || "—"}</span>
                      <StageBadge stage={b.stage} />
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                      <span className="font-mono">{(b.campaign_id || "").slice(0, 14)}...</span>
                      {pct > 0 && <span>{b.completed_tasks}/{b.total_tasks} ({pct}%)</span>}
                    </div>
                  </div>
                  <div className="shrink-0">
                    {b.stage === "in_review" && <Link to={`/labeling/review/${b.campaign_id}`}><Button size="small" variant="primary">▶ 开始质检</Button></Link>}
                    {b.stage === "review_approved" && <span className="text-green-600 text-sm font-medium">✓ 已通过</span>}
                    {b.stage === "review_rejected" && <span className="text-red-600 text-sm font-medium">✗ 已退回</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </PageQueryState>
    </div>
  );
};

// ── Detail ──
const ReviewDetailPage: React.FC<{ campaignId: string }> = ({ campaignId }) => {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [scores, setScores] = useState<ScoreCounts>({ good: 0, fine: 0, bad: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [localScores, setLocalScores] = useState<Record<string, string>>({});
  const [imgError, setImgError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ offset: "0", limit: "2000" });
      const res = await fetch(`/api/v1/labeling/campaigns/${campaignId}/review-queue?${params}`, {
        headers: { Authorization: `Bearer ${hsapApi.getToken()}` }, cache: "no-store",
      }).then((r) => r.json());
      setItems((res.items || []) as ReviewItem[]);
      setScores((res.scores || { good: 0, fine: 0, bad: 0, pending: 0 }) as ScoreCounts);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, [campaignId]);

  useEffect(() => { load(); }, [load]);

  const currentImage = items[currentIdx];
  const imageUrl = currentImage
    ? `/api/v1/labeling/campaigns/${campaignId}/review-image?path=${encodeURIComponent(currentImage.image_path)}`
    : "";
  const currentScore = currentImage ? (localScores[currentImage.image_path] || currentImage.score || "pending") : "pending";

  const handleScore = (score: string) => {
    if (!currentImage) return;
    setLocalScores((prev) => ({ ...prev, [currentImage.image_path]: score }));
    fetch(`/api/v1/labeling/campaigns/${campaignId}/review-submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${hsapApi.getToken()}` },
      body: JSON.stringify({ scores: [{ image_path: currentImage.image_path, score }] }),
    }).catch(() => {});
    setScores((prev) => {
      const oldScore = currentImage.score || "pending";
      const next = { ...prev };
      if (next[oldScore as ScoreKey] > 0) next[oldScore as ScoreKey]--;
      next[score as ScoreKey] = (next[score as ScoreKey] || 0) + 1;
      return next;
    });
    if (currentIdx < items.length - 1) setTimeout(() => setCurrentIdx((i) => i + 1), 250);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") setCurrentIdx((i) => Math.max(0, i - 1));
      else if (e.key === "ArrowRight") setCurrentIdx((i) => Math.min(items.length - 1, i + 1));
      else if (e.key === "g" || e.key === "G") handleScore("good");
      else if (e.key === "f" || e.key === "F") handleScore("fine");
      else if (e.key === "b" || e.key === "B") handleScore("bad");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [currentIdx, items.length]);

  const reviewed = scores.good + scores.fine + scores.bad;
  const total = reviewed + scores.pending;
  const progressPct = total > 0 ? (reviewed / total) * 100 : 0;
  const passRate = reviewed > 0 ? ((scores.good + scores.fine) / reviewed) * 100 : 0;

  return (
    <div className="flex flex-col h-screen bg-gray-900 text-white">
      {/* Top control bar */}
      <header className="flex items-center gap-4 px-4 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
        <Link to="/labeling/review" className="text-blue-400 text-sm hover:underline">← 返回列表</Link>
        <span className="text-gray-700">|</span>
        <span className="text-sm font-mono text-gray-300">{campaignId.slice(0, 16)}...</span>
        <span className="text-gray-700">|</span>
        {(["good", "fine", "bad"] as ScoreKey[]).map((k) => (
          <span key={k} className={`text-sm ${SCORE_CFG[k].color} flex items-center gap-1`}>
            <span className={`w-2.5 h-2.5 rounded-full ${SCORE_CFG[k].bg}`} />{SCORE_CFG[k].label}: {scores[k]}
          </span>
        ))}
        <div className="flex-1" />
        <span className="text-xs text-gray-500">{reviewed}/{total} 已评</span>
        <div className="w-24 h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${progressPct}%` }} />
        </div>
        <span className={`text-xs ${passRate >= 80 ? "text-green-400" : passRate > 0 ? "text-yellow-400" : "text-gray-500"}`}>
          {Math.round(passRate)}% 通过
        </span>
      </header>

      <PageQueryState loading={loading} error={error} empty={items.length === 0} emptyMessage="该批次暂无图片">
        {currentImage && (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Image */}
            <div className="flex-1 flex items-center justify-center p-4 min-h-0">
              {imgError ? (
                <div className="text-gray-500 text-center"><p className="text-lg mb-2">图片加载失败</p><p className="text-sm">{currentImage.fileName}</p></div>
              ) : (
                <img src={imageUrl} alt={currentImage.fileName} className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
                  onError={() => setImgError(true)} onLoad={() => setImgError(false)} />
              )}
            </div>

            {/* Bottom bar */}
            <div className="shrink-0 bg-gray-800 border-t border-gray-700 px-4 py-3">
              <div className="flex items-center gap-3 max-w-5xl mx-auto">
                <div className="flex items-center gap-2">
                  <Button variant="default" size="small" onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))} disabled={currentIdx <= 0}>←</Button>
                  <span className="text-sm text-gray-400 w-20 text-center tabular-nums">{currentIdx + 1}/{items.length}</span>
                  <Button variant="default" size="small" onClick={() => setCurrentIdx((i) => Math.min(items.length - 1, i + 1))} disabled={currentIdx >= items.length - 1}>→</Button>
                </div>
                <div className="flex-1" />
                {(["good", "fine", "bad"] as ScoreKey[]).map((s) => (
                  <button key={s} onClick={() => handleScore(s)}
                    className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all ${SCORE_CFG[s].btn} ${
                      currentScore === s ? "ring-2 ring-offset-2 ring-offset-gray-800 scale-105" : "hover:scale-105"
                    }`}>
                    {SCORE_CFG[s].icon} {SCORE_CFG[s].label}
                  </button>
                ))}
              </div>
              <div className="text-center mt-1.5 text-xs text-gray-500">
                {currentImage.fileName} · 标注: {currentImage.has_label ? "有" : "无"} · 快捷键: G/F/B 评分 ←→ 翻页
              </div>
            </div>
          </div>
        )}
      </PageQueryState>
    </div>
  );
};

// ── Router ──
export const QualityReviewPage: React.FC = () => {
  const { campaignId } = useParams<{ campaignId: string }>();
  if (!campaignId) return <ReviewListPage />;
  return <ReviewDetailPage campaignId={campaignId} />;
};
