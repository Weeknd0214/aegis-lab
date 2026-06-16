import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { CompactTableShell } from "@/components/CompactTableShell";
import { TruncatedText } from "@/components/TruncatedText";
import { displayProjectFields, displayTaskFields } from "@/lib/labelingDisplay";

export type MyAssignmentRow = {
  campaign_id: string;
  batch: string;
  task: string;
  project?: string;
  status?: string;
  assigned: number;
  completed: number;
  pending: number;
  campaign_total?: number;
};

type MyTasksTableProps = {
  items: MyAssignmentRow[];
  highlightId?: string | null;
};

const COLS = ["30%", "12%", "8%", "10%", "14%", "auto", "6rem"];

export const MyTasksTable: React.FC<MyTasksTableProps> = ({ items, highlightId }) => (
  <CompactTableShell colWidths={COLS}>
    <thead>
      <tr>
        <th className="py-2">批次</th>
        <th className="py-2">任务</th>
        <th className="py-2">项目</th>
        <th className="py-2">待标</th>
        <th className="py-2">进度</th>
        <th className="py-2">Campaign</th>
        <th className="py-2">操作</th>
      </tr>
    </thead>
    <tbody>
      {items.map((row) => {
        const pct = row.assigned > 0 ? Math.round((row.completed / row.assigned) * 100) : 0;
        const highlighted = highlightId === row.campaign_id;
        return (
          <tr
            key={row.campaign_id}
            className={`align-middle ${highlighted ? "bg-blue-50/60" : ""}`}
          >
            <td className="py-2 max-w-0">
              <TruncatedText text={row.batch || "—"} className="font-medium text-gray-900" maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText text={displayTaskFields(row)} maxWidthClass="max-w-full" />
            </td>
            <td className="py-2 whitespace-nowrap text-sm text-gray-700">{displayProjectFields(row)}</td>
            <td className="py-2 whitespace-nowrap">
              <span className="text-sm font-medium text-amber-600 tabular-nums">{row.pending}</span>
            </td>
            <td className="py-2 whitespace-nowrap">
                  <div className="flex items-center justify-center gap-1.5">
                <div className="w-14 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${pct >= 100 ? "bg-green-500" : "bg-blue-500"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs text-gray-500 tabular-nums">{row.completed}/{row.assigned}</span>
              </div>
            </td>
            <td className="py-2 max-w-0">
              <TruncatedText
                text={row.campaign_id || "—"}
                className="font-mono text-xs text-gray-500"
                maxWidthClass="max-w-full"
              />
            </td>
            <td className="py-2 px-2 whitespace-nowrap w-[6rem]">
              <Link to={`/labeling/annotate/${encodeURIComponent(row.campaign_id)}`}>
                <Button size="small" variant="primary" className="!px-2">
                  {row.pending > 0 ? "标注" : "查看"}
                </Button>
              </Link>
            </td>
          </tr>
        );
      })}
    </tbody>
  </CompactTableShell>
);
