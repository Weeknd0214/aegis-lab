import React from "react";

type Props = { counts: Record<string, number>; maxBars?: number; compact?: boolean };

export const ClassCountBars: React.FC<Props> = ({ counts, maxBars = 12, compact = false }) => {
  const entries = Object.entries(counts || {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxBars);
  if (!entries.length) return <p className="text-sm text-gray-400">暂无类别统计</p>;
  const max = Math.max(...entries.map(([, n]) => n), 1);

  return (
    <div className={compact ? "space-y-1" : "space-y-2"}>
      {entries.map(([name, n]) => (
        <div key={name} className={`flex items-center gap-2 ${compact ? "text-[11px]" : "text-sm"}`}>
          <span className={`truncate font-mono text-gray-500 shrink-0 ${compact ? "w-24" : "w-28"}`} title={name}>{name}</span>
          <div className={`flex-1 min-w-0 rounded-full bg-gray-100 overflow-hidden ${compact ? "h-2.5" : "h-2"}`}>
            <div className="h-full rounded-full bg-blue-700" style={{ width: `${Math.round((n / max) * 100)}%` }} />
          </div>
          <span className={`text-right tabular-nums shrink-0 ${compact ? "w-10" : "w-12"}`}>{n}</span>
        </div>
      ))}
    </div>
  );
};
