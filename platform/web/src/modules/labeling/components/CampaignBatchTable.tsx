import React from "react";
import { StageBadge } from "@/components/ui/Badge";
import { CompactTableShell } from "@/components/CompactTableShell";
import { TruncatedText } from "@/components/TruncatedText";
import { TableIconAction } from "./TableIconAction";
import { displayProject, displayTask } from "@/lib/labelingDisplay";
import type { LabelingBatchRow } from "@/lib/types";

type CampaignBatchTableProps = {
  batches: LabelingBatchRow[];
  expandCampaign: string | null;
  onToggleExpand: (campaignId: string) => void;
  onExport: (campaignId: string) => void;
  onSubmit: (campaignId: string) => void;
  renderExpand?: (b: LabelingBatchRow) => React.ReactNode;
};

const COLS = ["31%", "7%", "6%", "8%", "9%", "10%", "12.5rem"];

export const CampaignBatchTable: React.FC<CampaignBatchTableProps> = ({
  batches,
  expandCampaign,
  onToggleExpand,
  onExport,
  onSubmit,
  renderExpand,
}) => (
  <CompactTableShell colWidths={COLS}>
    <thead>
      <tr>
        <th className="py-2">批次</th>
        <th className="py-2">任务</th>
        <th className="py-2">项目</th>
        <th className="py-2">状态</th>
        <th className="py-2">进度</th>
        <th className="py-2">Campaign</th>
        <th className="py-2 w-[12.5rem]">操作</th>
      </tr>
    </thead>
    <tbody>
      {batches.map((b) => {
        const cid = b.campaign_id || "";
        const isExpanded = expandCampaign === cid;
        const canExport = ["labeling_submitted", "returned"].includes(b.stage || "");
        const pct =
          b.total_tasks && b.total_tasks > 0
            ? Math.round(((b.completed_tasks || 0) / b.total_tasks) * 100)
            : 0;

        return (
          <React.Fragment key={cid || b.batch}>
            <tr className={`align-middle ${isExpanded ? "bg-blue-50/40" : ""}`}>
              <td className="py-2 max-w-0 overflow-hidden">
                <TruncatedText text={b.batch || "—"} className="font-medium text-gray-900" maxWidthClass="max-w-full" />
              </td>
              <td className="py-2 max-w-0 overflow-hidden">
                <TruncatedText text={displayTask(b)} maxWidthClass="max-w-full" />
              </td>
              <td className="py-2 whitespace-nowrap text-sm text-gray-700">{displayProject(b)}</td>
              <td className="py-2 whitespace-nowrap">
                <StageBadge stage={b.stage} />
              </td>
              <td className="py-2 whitespace-nowrap">
                {b.total_tasks != null && b.total_tasks > 0 ? (
                  <div className="flex items-center justify-center gap-1 min-w-0">
                    <div className="w-10 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
                      <div
                        className={`h-full rounded-full ${pct >= 100 ? "bg-green-500" : "bg-blue-500"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-gray-500 tabular-nums">
                      {b.completed_tasks}/{b.total_tasks}
                    </span>
                  </div>
                ) : (
                  <span className="text-xs text-gray-400">—</span>
                )}
              </td>
              <td className="py-2 max-w-0 overflow-hidden">
                <TruncatedText text={cid || "—"} className="font-mono text-xs text-gray-500" maxWidthClass="max-w-full" />
              </td>
              <td className="py-2 px-0.5 align-middle w-[12.5rem]">
                {cid && (
                  <div className="inline-flex flex-nowrap items-center justify-center gap-0.5">
                    <TableIconAction
                      dense
                      to={`/labeling/annotate/${encodeURIComponent(cid)}`}
                      tone="blue"
                    >
                      ✏️ 标注
                    </TableIconAction>
                    <TableIconAction
                      dense
                      tone="gray"
                      disabled={!canExport}
                      title={canExport ? undefined : "质检通过后可导出"}
                      onClick={() => onExport(cid)}
                    >
                      📤 导出
                    </TableIconAction>
                    <TableIconAction dense tone="green" onClick={() => onSubmit(cid)}>
                      ✅ 质检
                    </TableIconAction>
                    <TableIconAction dense tone="purple" onClick={() => onToggleExpand(cid)}>
                      👥 {isExpanded ? "收起" : "分配"}
                    </TableIconAction>
                  </div>
                )}
              </td>
            </tr>
            {isExpanded && renderExpand && (
              <tr>
                <td colSpan={7} className="p-0 border-b border-gray-100 bg-gray-50/50">
                  {renderExpand(b)}
                </td>
              </tr>
            )}
          </React.Fragment>
        );
      })}
    </tbody>
  </CompactTableShell>
);
