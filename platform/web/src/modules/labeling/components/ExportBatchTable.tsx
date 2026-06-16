import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { CompactTableShell } from "@/components/CompactTableShell";
import { TruncatedText } from "@/components/TruncatedText";
import { displayProject, displayTask } from "@/lib/labelingDisplay";
import type { LabelingBatchRow } from "@/lib/types";

type ExportBatchTableProps = {
  batches: LabelingBatchRow[];
  importingId: string | null;
  buildingId: string | null;
  onExport: (campaignId: string) => void;
  onImportVendor: (campaignId: string) => void;
  onSubmitBuild: (batch: LabelingBatchRow) => void;
};

const COLS = ["34%", "14%", "8%", "10%", "auto", "7.5rem"];

export const ExportBatchTable: React.FC<ExportBatchTableProps> = ({
  batches,
  importingId,
  buildingId,
  onExport,
  onImportVendor,
  onSubmitBuild,
}) => (
  <CompactTableShell colWidths={COLS}>
    <thead>
      <tr>
        <th className="py-2">批次</th>
        <th className="py-2">任务</th>
        <th className="py-2">项目</th>
        <th className="py-2">状态</th>
        <th className="py-2">Campaign</th>
        <th className="py-2 w-[7.5rem]">操作</th>
      </tr>
    </thead>
    <tbody>
      {batches.map((b) => {
        const cid = b.campaign_id || "";
        const isExport = b.stage === "labeling_submitted";
        return (
          <tr key={cid || b.batch} className="align-middle">
            <td className="py-2 max-w-0">
              <TruncatedText text={b.batch || "—"} className="font-medium text-gray-900" maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText text={displayTask(b)} maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 whitespace-nowrap">
              <span className="text-sm text-gray-700">{displayProject(b)}</span>
            </td>
            <td className="py-2 whitespace-nowrap">
              <Badge variant="warning" size="small">
                {isExport ? "待导出" : "待入库"}
              </Badge>
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText
                text={cid || "—"}
                className="font-mono text-xs text-gray-500"
                maxWidthClass="max-w-full"
              />
            </td>
            <td className="py-2 px-2 whitespace-nowrap w-[7.5rem]">
              {cid && isExport && (
                <div className="inline-flex items-center justify-center gap-0.5">
                  <Button size="small" variant="primary" className="!px-2" onClick={() => onExport(cid)}>
                    导出
                  </Button>
                  <Button
                    size="small"
                    variant="default"
                    className="!px-2"
                    loading={importingId === cid}
                    onClick={() => onImportVendor(cid)}
                  >
                    导入
                  </Button>
                </div>
              )}
              {b.stage === "returned" && (
                <div className="inline-flex items-center justify-center gap-0.5">
                  <Button
                    size="small"
                    variant="primary"
                    className="!px-2"
                    loading={buildingId === (cid || b.batch)}
                    onClick={() => onSubmitBuild(b)}
                  >
                    入库
                  </Button>
                  <Link to="/system/audit">
                    <Button size="small" variant="default" className="!px-2">
                      审核
                    </Button>
                  </Link>
                </div>
              )}
            </td>
          </tr>
        );
      })}
    </tbody>
  </CompactTableShell>
);
