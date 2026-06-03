import React from "react";

interface BadgeProps {
  variant?: "default" | "success" | "warning" | "danger" | "info";
  size?: "small" | "medium";
  className?: string;
  children: React.ReactNode;
}

const variantClasses: Record<string, string> = {
  default: "bg-gray-100 text-gray-700",
  success: "bg-green-100 text-green-800",
  warning: "bg-yellow-100 text-yellow-800",
  danger: "bg-red-100 text-red-800",
  info: "bg-blue-100 text-blue-800",
};

const sizeClasses = {
  small: "px-1.5 py-0.5 text-[10px]",
  medium: "px-2.5 py-1 text-xs",
};

export const Badge: React.FC<BadgeProps> = ({
  variant = "default",
  size = "medium",
  className = "",
  children,
}) => {
  const cls = [
    "inline-flex items-center font-medium rounded-full whitespace-nowrap",
    variantClasses[variant] || variantClasses.default,
    sizeClasses[size],
    className,
  ].join(" ");

  return <span className={cls}>{children}</span>;
};

/** Stage badge — maps batch stages to colors */
export const StageBadge: React.FC<{ stage: string }> = ({ stage }) => {
  const map: Record<string, { variant: BadgeProps["variant"]; label: string }> = {
    raw_pool: { variant: "default", label: "待标注" },
    out_for_labeling: { variant: "info", label: "标中" },
    labeling_submitted: { variant: "warning", label: "已提交" },
    returned: { variant: "success", label: "待入库" },
    ingested: { variant: "success", label: "已入库" },
    in_review: { variant: "warning", label: "质检中" },
    review_approved: { variant: "success", label: "质检通过" },
    review_rejected: { variant: "danger", label: "质检退回" },
  };
  const m = map[stage] || { variant: "default" as const, label: stage };
  return <Badge variant={m.variant}>{m.label}</Badge>;
};

/** Status badge for approvals, jobs, deliveries */
export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const map: Record<string, { variant: BadgeProps["variant"]; label: string }> = {
    pending: { variant: "warning", label: "待审核" },
    approved: { variant: "success", label: "已通过" },
    rejected: { variant: "danger", label: "已驳回" },
    running: { variant: "info", label: "执行中" },
    completed: { variant: "success", label: "已完成" },
    failed: { variant: "danger", label: "失败" },
    draft: { variant: "default", label: "草稿" },
    submitted: { variant: "info", label: "已提交" },
    ingested: { variant: "success", label: "已入湖" },
    cancelled: { variant: "default", label: "已取消" },
  };
  const m = map[status] || { variant: "default" as const, label: status };
  return <Badge variant={m.variant}>{m.label}</Badge>;
};
