import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { CompactTableShell } from "@/components/CompactTableShell";
import { TruncatedText } from "@/components/TruncatedText";
import { displayProjectFields, displayTaskFields } from "@/lib/labelingDisplay";
import type { BatchDelivery } from "@/lib/types";

const SOURCE_LABELS: Record<string, string> = {
  inbox_scan: "inbox扫描",
  platform_delivery: "NAS送标",
  upload: "页面上传",
  feishu_bitable: "飞书",
};

function formatSource(st?: string | null, d?: BatchDelivery): string {
  if (!st) return "—";
  if (d?.project === "adas" && d?.task === "det_7cls") return "ADAS 2D";
  if (d?.project === "dms" && d?.task === "adas") return "ADAS 2D";
  if (d?.project === "adas" && d?.task === "cuboid_7cls") return "ADAS 3D";
  return SOURCE_LABELS[st] || st;
}

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

type DeliveryTableProps = {
  deliveries: BatchDelivery[];
  canSubmit: boolean;
  onSubmit: (id: string) => void;
  onDelete: (id: string) => void;
};

const COLS = ["22%", "8%", "8%", "8%", "9%", "10%", "9%", "9%", "7.5rem"];

export const DeliveryTable: React.FC<DeliveryTableProps> = ({
  deliveries,
  canSubmit,
  onSubmit,
  onDelete,
}) => (
  <CompactTableShell colWidths={COLS}>
    <thead>
      <tr>
        <th className="py-2">批次</th>
        <th className="py-2">来源</th>
        <th className="py-2">项目</th>
        <th className="py-2">任务</th>
        <th className="py-2">状态</th>
        <th className="py-2">采集周期</th>
        <th className="py-2">数量</th>
        <th className="py-2">登记时间</th>
        <th className="py-2">操作</th>
      </tr>
    </thead>
    <tbody>
      {deliveries.map((d) => {
        const period = d.collection_start
          ? `${formatDate(d.collection_start)}${d.collection_end ? ` ~ ${formatDate(d.collection_end)}` : ""}`
          : "—";
        return (
          <tr key={d.id} className="align-middle">
            <td className="py-2 max-w-0">
              <TruncatedText text={d.batch_name || "—"} className="font-medium text-gray-900" maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 whitespace-nowrap text-xs text-gray-600">{formatSource(d.source_type, d)}</td>
            <td className="py-2 whitespace-nowrap text-sm text-gray-700">
              {displayProjectFields({ project: d.project, task: d.task || undefined })}
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText
                text={displayTaskFields({ project: d.project, task: d.task || undefined })}
                maxWidthClass="max-w-full"
              />
            </td>
            <td className="py-2 whitespace-nowrap">
              <StatusBadge status={d.status} />
            </td>
            <td className="py-2 whitespace-nowrap text-xs text-gray-500">{period}</td>
            <td className="py-2 text-sm text-gray-600 tabular-nums">{d.estimated_count ?? "—"}</td>
            <td className="py-2 whitespace-nowrap text-xs text-gray-500">{formatDate(d.created_at)}</td>
            <td className="py-2 px-2 whitespace-nowrap w-[7.5rem]">
              <div className="inline-flex items-center justify-center gap-0.5 flex-wrap">
                {d.status === "draft" && canSubmit && (
                  <>
                    <Button size="small" variant="primary" className="!px-2" onClick={() => onSubmit(d.id)}>
                      提交
                    </Button>
                    <Button size="small" variant="danger" className="!px-2" onClick={() => onDelete(d.id)}>
                      删除
                    </Button>
                  </>
                )}
                {d.status === "in_lake" && (
                  <Link to="/labeling/workbench">
                    <Button size="small" variant="success" className="!px-2">开标</Button>
                  </Link>
                )}
                {d.approval_id && (
                  <Link to={`/system/audit/${d.approval_id}`}>
                    <Button size="small" variant="default" className="!px-2">审核</Button>
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
