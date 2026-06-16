import React from "react";
import { Link } from "react-router-dom";

const BASE =
  "inline-flex items-center gap-0.5 font-medium rounded-lg transition-colors whitespace-nowrap shrink-0";

type TableIconActionProps = {
  children: React.ReactNode;
  title?: string;
  disabled?: boolean;
  onClick?: () => void;
  to?: string;
  tone?: "blue" | "gray" | "green" | "purple" | "danger";
  /** 略收紧的内边距，仍保留图标+文字 */
  dense?: boolean;
};

const TONE: Record<NonNullable<TableIconActionProps["tone"]>, string> = {
  blue: "bg-blue-50 text-blue-700 hover:bg-blue-100",
  gray: "bg-gray-50 text-gray-600 hover:bg-gray-100",
  green: "bg-green-50 text-green-700 hover:bg-green-100",
  purple: "bg-purple-50 text-purple-700 hover:bg-purple-100",
  danger: "bg-red-50 text-red-700 hover:bg-red-100",
};

const DISABLED = "bg-gray-50 text-gray-300 cursor-not-allowed pointer-events-none";

export const TableIconAction: React.FC<TableIconActionProps> = ({
  children,
  title,
  disabled,
  onClick,
  to,
  tone = "gray",
  dense = false,
}) => {
  const cls = `${BASE} ${dense ? "px-1.5 py-1 text-[11px] leading-tight" : "px-2 py-1.5 text-xs"} ${
    disabled ? DISABLED : TONE[tone]
  }`;
  if (to && !disabled) {
    return (
      <Link to={to} className={cls} title={title}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className={cls} title={title} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
};
