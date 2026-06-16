import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { StageBadge } from "@/components/ui/Badge";
import { CompactTableShell } from "@/components/CompactTableShell";
import { TruncatedText } from "@/components/TruncatedText";
import { displayProject, displayTask } from "@/lib/labelingDisplay";
import type { LabelingBatchRow } from "@/lib/types";

type ReviewProgress = {
  total: number;
  reviewed: number;
  good: number;
  fine: number;
  bad: number;
  pass_rate: number;
  complete: boolean;
  stage?: string;
};

type ReviewBatchTableProps = {
  batches: LabelingBatchRow[];
  progressMap: Record<string, ReviewProgress>;
};

const COLS = ["30%", "12%", "8%", "10%", "14%", "auto", "7.5rem"];

export const ReviewBatchTable: React.FC<ReviewBatchTableProps> = ({ batches, progressMap }) => (
  <CompactTableShell colWidths={COLS}>
    <thead>
      <tr>
        <th className="py-2">批次</th>
        <th className="py-2">任务</th>
        <th className="py-2">项目</th>
        <th className="py-2">状态</th>
        <th className="py-2">进度</th>
        <th className="py-2">Campaign</th>
        <th className="py-2">操作</th>
      </tr>
    </thead>
    <tbody>
      {batches.map((b) => {
        const cid = b.campaign_id || "";
        const prog = cid ? progressMap[cid] : undefined;
        const reviewPct = prog && prog.total > 0 ? Math.round((prog.reviewed / prog.total) * 100) : 0;
        const reviewDone = prog?.complete;
        const effectiveStage = reviewDone && prog?.stage ? prog.stage : b.stage;
        const passed = effectiveStage === "labeling_submitted" || (reviewDone && (prog?.pass_rate ?? 0) >= 80);
        return (
          <tr key={cid || b.batch} className="align-middle">
            <td className="py-2 max-w-0">
              <TruncatedText text={b.batch || "—"} className="font-medium text-gray-900" maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText text={displayTask(b)} maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 whitespace-nowrap text-sm text-gray-700">{displayProject(b)}</td>
            <td className="py-2 whitespace-nowrap">
              <StageBadge stage={effectiveStage || ""} />
            </td>
            <td className="py-2 whitespace-nowrap">
              {prog && prog.total > 0 ? (
                  <div className="flex items-center justify-center gap-1.5 min-w-0">
                  <div className="w-14 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
                    <div
                      className={`h-full rounded-full ${reviewDone ? "bg-green-500" : "bg-blue-500"}`}
                      style={{ width: `${reviewPct}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500 tabular-nums">{prog.reviewed}/{prog.total}</span>
                  {reviewDone && (
                    <span className={`text-xs ${passed ? "text-green-600" : "text-red-600"}`}>
                      {prog.pass_rate}%
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-xs text-gray-400">—</span>
              )}
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText text={cid || "—"} className="font-mono text-xs text-gray-500" maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 px-2 whitespace-nowrap w-[7.5rem]">
              <div className="flex justify-center">
              {effectiveStage === "in_review" && cid && (
                <Link to={`/labeling/review/${cid}`}>
                  <Button size="small" variant="primary" className="!px-2">
                    {reviewDone ? "查看" : prog && prog.reviewed > 0 ? "继续" : "质检"}
                  </Button>
                </Link>
              )}
              {effectiveStage === "labeling_submitted" && (
                <Link to="/labeling/export">
                  <Button size="small" variant="success" className="!px-2">导出</Button>
                </Link>
              )}
              {effectiveStage === "review_rejected" && cid && (
                <Link to={`/labeling/review/${cid}`}>
                  <Button size="small" variant="default" className="!px-2">记录</Button>
                </Link>
              )}
              </div>
            </td>
          </tr>
        );
      })}
    </tbody>
  </CompactTableShell>
);
