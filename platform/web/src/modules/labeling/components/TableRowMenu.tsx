import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

export type TableRowMenuItem = {
  key: string;
  label: string;
  icon?: string;
  onClick?: () => void;
  to?: string;
  disabled?: boolean;
  title?: string;
};

const TONE: Record<string, string> = {
  blue: "bg-blue-50 text-blue-700 hover:bg-blue-100",
  green: "bg-green-50 text-green-700 hover:bg-green-100",
  purple: "bg-purple-50 text-purple-700 hover:bg-purple-100",
  gray: "bg-gray-50 text-gray-600 hover:bg-gray-100",
};

type TableRowMenuProps = {
  primary?: TableRowMenuItem & { tone?: keyof typeof TONE };
  items?: TableRowMenuItem[];
};

const PrimaryBtn: React.FC<{ item: TableRowMenuItem & { tone?: keyof typeof TONE } }> = ({ item }) => {
  const cls = `inline-flex items-center gap-1 px-2 py-1.5 text-xs font-medium rounded-lg transition-colors whitespace-nowrap shrink-0 ${
    item.disabled ? "bg-gray-50 text-gray-300 cursor-not-allowed pointer-events-none" : TONE[item.tone || "blue"]
  }`;
  const content = (
    <>
      {item.icon && <span>{item.icon}</span>}
      <span>{item.label}</span>
    </>
  );
  if (item.to && !item.disabled) {
    return <Link to={item.to} className={cls} title={item.title}>{content}</Link>;
  }
  return (
    <button type="button" className={cls} title={item.title} disabled={item.disabled} onClick={item.onClick}>
      {content}
    </button>
  );
};

export const TableRowMenu: React.FC<TableRowMenuProps> = ({ primary, items = [] }) => {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const renderMenuItem = (item: TableRowMenuItem) => {
    const cls = `flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors ${
      item.disabled ? "text-gray-300 cursor-not-allowed" : "text-gray-700 hover:bg-gray-50"
    }`;
    const content = (
      <>
        {item.icon && <span className="shrink-0">{item.icon}</span>}
        <span>{item.label}</span>
      </>
    );
    if (item.to && !item.disabled) {
      return (
        <Link key={item.key} to={item.to} className={cls} title={item.title} onClick={() => setOpen(false)}>
          {content}
        </Link>
      );
    }
    return (
      <button
        key={item.key}
        type="button"
        className={cls}
        title={item.title}
        disabled={item.disabled}
        onClick={() => {
          if (item.disabled) return;
          item.onClick?.();
          setOpen(false);
        }}
      >
        {content}
      </button>
    );
  };

  return (
    <div ref={rootRef} className="relative inline-flex items-center justify-end gap-0.5">
      {primary && <PrimaryBtn item={primary} />}
      {items.length > 0 && (
        <>
          <button
            type="button"
            className="inline-flex items-center justify-center w-7 h-7 text-xs font-medium rounded-lg bg-gray-50 text-gray-500 hover:bg-gray-100 shrink-0"
            title="更多操作"
            onClick={() => setOpen((v) => !v)}
          >
            ⋮
          </button>
          {open && (
            <div className="absolute right-0 top-full z-30 mt-1 min-w-[9.5rem] rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
              {items.map(renderMenuItem)}
            </div>
          )}
        </>
      )}
    </div>
  );
};
