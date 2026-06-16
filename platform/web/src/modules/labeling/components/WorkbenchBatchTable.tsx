import React from "react";
import { StageBadge } from "@/components/ui/Badge";
import { CompactTableShell } from "@/components/CompactTableShell";
import { TruncatedText } from "@/components/TruncatedText";
import { TableIconAction } from "./TableIconAction";
import { displayProject, displayTask } from "@/lib/labelingDisplay";
import type { LabelingBatchRow } from "@/lib/types";

type WorkbenchBatchTableProps = {
  batches: LabelingBatchRow[];
  onOpenCampaign: (row: LabelingBatchRow) => void;
  onArchive?: (row: LabelingBatchRow) => void;
  archivingId?: string | null;
};

const COLS = ["32%", "9%", "7%", "9%", "7%", "7%", "11rem"];

export const WorkbenchBatchTable: React.FC<WorkbenchBatchTableProps> = ({
  batches,
  onOpenCampaign,
  onArchive,
  archivingId,
}) => (
  <CompactTableShell colWidths={COLS}>
    <thead>
      <tr>
        <th className="py-2">批次</th>
        <th className="py-2">任务</th>
        <th className="py-2">项目</th>
        <th className="py-2">状态</th>
        <th className="py-2">图片</th>
        <th className="py-2">标注</th>
        <th className="py-2 w-[11rem]">操作</th>
      </tr>
    </thead>
    <tbody>
      {batches.map((b) => {
        const cid = b.campaign_id || "";
        return (
          <tr key={`${b.project}/${b.task}/${b.batch}`} className="align-middle">
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
            <td className="py-2 text-sm text-gray-600 tabular-nums">{b.counts?.images ?? 0}</td>
            <td className="py-2 text-sm text-gray-600 tabular-nums">{b.counts?.labels ?? 0}</td>
            <td className="py-2 px-0.5 whitespace-nowrap w-[11rem]">
              <div className="inline-flex flex-nowrap items-center justify-center gap-0.5">
                {b.stage === "raw_pool" && (
                  <>
                    <TableIconAction dense tone="blue" onClick={() => onOpenCampaign(b)}>
                      📂 开标
                    </TableIconAction>
                    {onArchive && (
                      <TableIconAction
                        dense
                        tone="danger"
                        disabled={archivingId === cid}
                        onClick={() => onArchive(b)}
                      >
                        🗑 移除
                      </TableIconAction>
                    )}
                  </>
                )}
                {b.stage === "out_for_labeling" && cid && (
                  <>
                    <TableIconAction
                      dense
                      to={`/labeling/annotate/${encodeURIComponent(cid)}`}
                      tone="blue"
                    >
                      ✏️ 标注
                    </TableIconAction>
                    <TableIconAction dense to="/labeling/campaigns" tone="gray">
                      📊 进度
                    </TableIconAction>
                  </>
                )}
                {b.stage === "returned" && (
                  <TableIconAction dense to="/labeling/export" tone="gray">
                    🏗 入库
                  </TableIconAction>
                )}
              </div>
            </td>
          </tr>
        );
      })}
    </tbody>
  </CompactTableShell>
);
