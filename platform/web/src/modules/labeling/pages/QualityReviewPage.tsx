import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import { LabelingListToolbar } from "../components/LabelingListToolbar";
import { ReviewBatchTable } from "../components/ReviewBatchTable";
import type { LabelingBatchRow } from "@/lib/types";

type ReviewItem = { id: string; image_path: string; fileName: string; score: string; has_label: boolean };
type ScoreCounts = { good: number; fine: number; bad: number; pending: number };
type ScoreKey = keyof ScoreCounts;
type ReviewProgress = ScoreCounts & { total: number; reviewed: number; pass_rate: number; complete: boolean; stage?: string };

const SCORE_CFG: Record<ScoreKey, { label: string; color: string; bg: string; icon: string; btn: string }> = {
  good: { label: "合格", color: "text-green-600", bg: "bg-green-500", icon: "✓", btn: "bg-green-600 hover:bg-green-500 text-white" },
  fine: { label: "可用", color: "text-yellow-600", bg: "bg-yellow-500", icon: "~", btn: "bg-yellow-600 hover:bg-yellow-500 text-white" },
  bad: { label: "退回", color: "text-red-600", bg: "bg-red-500", icon: "✗", btn: "bg-red-600 hover:bg-red-500 text-white" },
  pending: { label: "未评", color: "text-gray-400", bg: "bg-gray-300", icon: "○", btn: "" },
};

const NAV_BTN =
  "inline-flex items-center justify-center gap-1.5 min-w-[5.5rem] px-3 py-2 rounded-lg text-sm font-medium transition-all " +
  "bg-gray-700/90 text-gray-100 border border-gray-600 " +
  "hover:bg-gray-600 hover:border-gray-500 active:scale-[0.98] " +
  "disabled:opacity-35 disabled:cursor-not-allowed disabled:hover:bg-gray-700/90 disabled:active:scale-100";

const STAGE_FILTERS = [
  { label: "全部", value: "" },
  { label: "质检中", value: "in_review" },
  { label: "已通过", value: "labeling_submitted" },
  { label: "已退回", value: "review_rejected" },
];

// ── List ──
const ReviewListPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [progressMap, setProgressMap] = useState<Record<string, ReviewProgress>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [rebuilding, setRebuilding] = useState(false);
  const [indexedAt, setIndexedAt] = useState<string | null>(null);

  const loadProgress = useCallback(async (rows: LabelingBatchRow[]) => {
    const ids = rows.map((b) => b.campaign_id).filter(Boolean) as string[];
    if (!ids.length) {
      setProgressMap({});
      return;
    }
    try {
      const res = await hsapApi.reviewProgressBatch(ids);
      setProgressMap((res.items || {}) as Record<string, ReviewProgress>);
    } catch {
      setProgressMap({});
    }
  }, []);

  const load = useCallback(async (newOffset: number, newLimit: number) => {
    setLoading(true);
    setError(null);
    try {
      const q = search.trim() || undefined;
      const res = await hsapApi.labelingBatches(
        stageFilter
          ? { stage: stageFilter, offset: newOffset, limit: newLimit, q }
          : { stages: ["in_review", "labeling_submitted", "review_rejected"], offset: newOffset, limit: newLimit, q },
      );
      const results = (res.items || []) as LabelingBatchRow[];
      setBatches(results);
      setTotal(res.total ?? 0);
      setOffset(newOffset);
      setLimit(newLimit);
      setIndexedAt(res.updated_at || null);
      await loadProgress(results);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [search, stageFilter, loadProgress]);

  useEffect(() => { void load(0, limit); }, [search, stageFilter]);

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await hsapApi.rebuildBatchIndex();
      await load(offset, limit);
    } catch (e) {
      setError(String(e));
    }
    setRebuilding(false);
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>标注质检</h1>
          <p>审核标注质量 — 合格和可用的流入训练集，退回的返回标注员修正</p>
        </div>
        <div className="flex items-center gap-2">
          {indexedAt && <span className="text-xs text-gray-400">索引 {indexedAt.slice(11, 19)}</span>}
          <Button size="small" variant="default" onClick={() => load(offset, limit)} disabled={loading}>刷新</Button>
          <Button size="small" variant="default" onClick={handleRebuild} loading={rebuilding}>同步磁盘</Button>
        </div>
      </div>

      <LabelingListToolbar
        search={search}
        onSearchChange={setSearch}
        placeholder="搜索批次/任务/项目..."
        filters={STAGE_FILTERS}
        filterValue={stageFilter}
        onFilterChange={setStageFilter}
        total={total}
      />

      <PageQueryState loading={loading} error={error} empty={!loading && total === 0} emptyMessage="暂无待质检的批次">
        {total > 0 && (
          <>
            <ReviewBatchTable batches={batches} progressMap={progressMap} />
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
    </div>
  );
};

// ── Detail ──
const ReviewDetailPage: React.FC<{ campaignId: string }> = ({ campaignId }) => {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [totalImages, setTotalImages] = useState(0);
  const [scores, setScores] = useState<ScoreCounts>({ good: 0, fine: 0, bad: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [localScores, setLocalScores] = useState<Record<string, string>>({});
  const [imgError, setImgError] = useState(false);
  const [imageBlobUrl, setImageBlobUrl] = useState<string | null>(null);
  const [imgLoading, setImgLoading] = useState(false);
  const [finishState, setFinishState] = useState<"approved" | "rejected" | null>(null);

  const loadPage = useCallback(async (idx: number) => {
    setLoading(true); setError(null);
    try {
      const data = await hsapApi.reviewQueue(campaignId, { offset: idx, limit: 1 });
      setItems((data.items || []) as ReviewItem[]);
      setTotalImages(Number(data.total) || 0);
      if (data.scores) setScores(data.scores as ScoreCounts);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, [campaignId]);

  useEffect(() => { loadPage(currentIdx); }, [currentIdx, loadPage]);

  const currentImage = items[currentIdx];
  const currentScore = currentImage ? (localScores[currentImage.image_path] || currentImage.score || "pending") : "pending";

  useEffect(() => {
    if (!currentImage) {
      setImageBlobUrl(null);
      return;
    }
    let cancelled = false;
    setImgLoading(true);
    setImgError(false);
    hsapApi.fetchReviewImageBlob(campaignId, currentImage.image_path)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        setImageBlobUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
        setImgLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setImgError(true);
          setImageBlobUrl(null);
          setImgLoading(false);
        }
      });
    return () => {
      cancelled = true;
      setImageBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [campaignId, currentImage?.image_path]);

  const handleScore = (score: string) => {
    if (!currentImage) return;
    setLocalScores((prev) => ({ ...prev, [currentImage.image_path]: score }));
    hsapApi.reviewSubmit(campaignId, [{ image_path: currentImage.image_path, score }])
      .then((data) => {
        if (data.auto_advanced) {
          setFinishState(data.stage === "review_approved" ? "approved" : "rejected");
        }
      })
      .catch(() => {});
    setScores((prev) => {
      const oldScore = currentImage.score || "pending";
      const next = { ...prev };
      if (next[oldScore as ScoreKey] > 0) next[oldScore as ScoreKey]--;
      next[score as ScoreKey] = (next[score as ScoreKey] || 0) + 1;
      if (oldScore === "pending" && next.pending > 0) next.pending--;
      return next;
    });
    if (currentIdx < totalImages - 1) setTimeout(() => setCurrentIdx((i) => i + 1), 250);
  };

  const reviewComplete = scores.pending === 0 && totalImages > 0;
  const reviewPassed = finishState === "approved" || (reviewComplete && (scores.good + scores.fine) / totalImages >= 0.8);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") setCurrentIdx((i) => Math.max(0, i - 1));
      else if (e.key === "ArrowRight") setCurrentIdx((i) => Math.min(totalImages - 1, i + 1));
      else if (e.key === "g" || e.key === "G") handleScore("good");
      else if (e.key === "f" || e.key === "F") handleScore("fine");
      else if (e.key === "b" || e.key === "B") handleScore("bad");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [currentIdx, totalImages]);

  const reviewed = scores.good + scores.fine + scores.bad;
  const total = reviewed + scores.pending;
  const progressPct = total > 0 ? (reviewed / total) * 100 : 0;
  const passRate = reviewed > 0 ? ((scores.good + scores.fine) / reviewed) * 100 : 0;

  return (
    <div className="flex flex-col flex-1 min-h-0 h-full overflow-hidden bg-gray-900 text-white">
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

      {(reviewComplete || finishState) && (
        <div className={`shrink-0 px-4 py-2.5 flex items-center justify-between gap-3 text-sm ${
          reviewPassed ? "bg-green-900/40 border-b border-green-700/50" : "bg-red-900/40 border-b border-red-700/50"
        }`}>
          <span className={reviewPassed ? "text-green-300" : "text-red-300"}>
            {reviewPassed
              ? `质检完成：合格+可用 ${scores.good + scores.fine}/${totalImages}（通过率 ${Math.round(((scores.good + scores.fine) / totalImages) * 100)}%），可进入导出入库`
              : `质检完成：退回 ${scores.bad} 张，批次已退回标注员修正`}
          </span>
          {reviewPassed ? (
            <Link to="/labeling/export">
              <Button size="small" variant="success">前往导出入库 →</Button>
            </Link>
          ) : (
            <Link to="/labeling/review">
              <Button size="small" variant="ghost">返回列表</Button>
            </Link>
          )}
        </div>
      )}

      <PageQueryState loading={loading} error={error} empty={!loading && totalImages === 0} emptyMessage="该批次暂无图片">
        {currentImage && (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            {/* Image */}
            <div className="flex-1 flex items-center justify-center p-4 min-h-0 overflow-hidden">
              {imgLoading ? (
                <div className="text-gray-400 text-center"><p className="text-lg mb-2">加载预览中...</p></div>
              ) : imgError || !imageBlobUrl ? (
                <div className="text-gray-500 text-center"><p className="text-lg mb-2">图片加载失败</p><p className="text-sm">{currentImage.fileName}</p></div>
              ) : (
                <img src={imageBlobUrl} alt={currentImage.fileName} className="max-w-full max-h-full object-contain rounded-lg shadow-2xl" />
              )}
            </div>

            {/* Bottom bar — 始终贴在可视区域底部 */}
            <div className="shrink-0 bg-gray-800 border-t border-gray-700 px-4 py-3 safe-area-pb">
              <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3 max-w-5xl mx-auto">
                <div className="inline-flex items-center gap-1 p-1 rounded-xl bg-gray-900/70 border border-gray-700/80 shadow-inner">
                  <button
                    type="button"
                    className={NAV_BTN}
                    onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
                    disabled={currentIdx <= 0}
                    aria-label="上一张"
                  >
                    <span aria-hidden>‹</span> 上一张
                  </button>
                  <span className="px-3 py-1.5 text-sm font-semibold text-gray-200 tabular-nums min-w-[4.5rem] text-center select-none">
                    {currentIdx + 1}<span className="text-gray-500 font-normal mx-1">/</span>{totalImages}
                  </span>
                  <button
                    type="button"
                    className={NAV_BTN}
                    onClick={() => setCurrentIdx((i) => Math.min(totalImages - 1, i + 1))}
                    disabled={currentIdx >= totalImages - 1}
                    aria-label="下一张"
                  >
                    下一张 <span aria-hidden>›</span>
                  </button>
                </div>
                <div className="hidden sm:block flex-1" />
                <div className="flex flex-wrap items-center justify-center gap-2 w-full sm:w-auto">
                {(["good", "fine", "bad"] as ScoreKey[]).map((s) => (
                  <button key={s} onClick={() => handleScore(s)}
                    className={`px-5 py-2.5 rounded-lg font-semibold text-sm transition-all ${SCORE_CFG[s].btn} ${
                      currentScore === s ? "ring-2 ring-offset-2 ring-offset-gray-800 scale-105" : "hover:scale-105"
                    }`}>
                    {SCORE_CFG[s].icon} {SCORE_CFG[s].label}
                  </button>
                ))}
                </div>
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
