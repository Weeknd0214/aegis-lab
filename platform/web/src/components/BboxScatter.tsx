import React from "react";
import { CHART_EMPTY_HINT } from "@/lib/chartStats";

type Props = { points: [number, number][]; size?: number; maxPoints?: number; compact?: boolean };

export const BboxScatter: React.FC<Props> = ({ points, size = 220, maxPoints = 800, compact = false }) => {
  const sample = points.length > maxPoints ? points.slice(0, maxPoints) : points;
  if (!sample.length) return <p className="text-sm text-gray-400 m-0">{CHART_EMPTY_HINT}</p>;

  const pad = compact ? 22 : 28;
  const w = size, h = size;
  const plotW = w - pad * 2, plotH = h - pad * 2;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={pad} y={pad} width={plotW} height={plotH} fill="none" stroke="#d1d5db" strokeOpacity={0.3} />
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={pad + t * plotW} y1={pad} x2={pad + t * plotW} y2={pad + plotH} stroke="#d1d5db" strokeOpacity={0.08} />
            <line x1={pad} y1={pad + (1 - t) * plotH} x2={pad + plotW} y2={pad + (1 - t) * plotH} stroke="#d1d5db" strokeOpacity={0.08} />
          </g>
        ))}
        {sample.map(([bw, bh], i) => (
          <circle key={i} cx={pad + Math.min(1, Math.max(0, bw)) * plotW} cy={pad + (1 - Math.min(1, Math.max(0, bh))) * plotH}
            r={1.8} fill="#2563eb" fillOpacity={0.55} />
        ))}
        <text x={w / 2} y={h - 6} textAnchor="middle" className="fill-gray-400 text-[10px]">宽 w</text>
        <text x={10} y={h / 2} textAnchor="middle" transform={`rotate(-90 10 ${h / 2})`} className="fill-gray-400 text-[10px]">高 h</text>
      </svg>
      {!compact && points.length > maxPoints && (
        <p className="text-sm text-gray-400 m-0">采样展示 {maxPoints} / {points.length} 点</p>
      )}
    </div>
  );
};
