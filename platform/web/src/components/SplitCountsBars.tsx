import React from "react";
import { CHART_EMPTY_HINT } from "@/lib/chartStats";
import type { SplitCounts } from "@/lib/dmsCatalog";

type Props = { counts: SplitCounts; height?: number };

const LABELS: { key: keyof SplitCounts; label: string }[] = [
  { key: "train", label: "train" }, { key: "val", label: "val" }, { key: "test", label: "test" },
];

export const SplitCountsBars: React.FC<Props> = ({ counts, height = 120 }) => {
  const total = counts.train + counts.val + counts.test;
  if (total <= 0) return <p className="text-sm text-gray-400 m-0">{CHART_EMPTY_HINT}</p>;

  const max = Math.max(counts.train, counts.val, counts.test, 1);
  const barW = 48;

  return (
    <div className="flex items-end gap-6 justify-center" style={{ height }}>
      {LABELS.map(({ key, label }) => {
        const n = counts[key];
        return (
          <div key={key} className="flex flex-col items-center" style={{ width: barW }}>
            <span className="text-sm tabular-nums font-semibold mb-1">{n}</span>
            <div className="w-full rounded-t bg-blue-700" style={{ height: `${Math.max(8, Math.round((n / max) * (height - 48)))}px` }} />
            <span className="text-xs text-gray-500 mt-2 font-mono">{label}</span>
          </div>
        );
      })}
    </div>
  );
};
