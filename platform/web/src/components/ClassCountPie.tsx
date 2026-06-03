import React, { useRef, useState } from "react";
import { CHART_EMPTY_HINT, pieSlices } from "@/lib/chartStats";

type Props = { counts: Record<string, number>; size?: number };

type ArcSlice = { name: string; value: number; pct: number; d: string };
type PieTip = { name: string; value: number; pct: number; x: number; y: number };

const COLORS = ["#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#1d4ed8", "#1e40af", "#6366f1", "#818cf8", "#94a3b8"];

export const ClassCountPie: React.FC<Props> = ({ counts, size = 200 }) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<PieTip | null>(null);

  const entries = Object.entries(counts || {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
  const slices = pieSlices(entries);
  if (!slices.length) return <p className="text-sm text-gray-400 m-0">{CHART_EMPTY_HINT}</p>;

  const cx = size / 2, cy = size / 2, r = size * 0.38, ir = r * 0.45;
  let angle = -Math.PI / 2;

  const arcs: ArcSlice[] = slices.map((s) => {
    const sweep = s.pct * 2 * Math.PI;
    const x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle);
    const x2 = cx + r * Math.cos(angle + sweep), y2 = cy + r * Math.sin(angle + sweep);
    const xi1 = cx + ir * Math.cos(angle + sweep), yi1 = cy + ir * Math.sin(angle + sweep);
    const xi2 = cx + ir * Math.cos(angle), yi2 = cy + ir * Math.sin(angle);
    const large = sweep > Math.PI ? 1 : 0;
    const d = [`M ${x1} ${y1}`, `A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`, `L ${xi1} ${yi1}`, `A ${ir} ${ir} 0 ${large} 0 ${xi2} ${yi2}`, "Z"].join(" ");
    angle += sweep;
    return { ...s, d };
  });

  return (
    <div ref={wrapRef} className="relative flex items-center justify-center" onMouseLeave={() => setTip(null)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
        {arcs.map((a, i) => (
          <path key={a.name} d={a.d} fill={COLORS[i % COLORS.length]} stroke="#fff" strokeWidth={1}
            className="cursor-pointer transition-opacity" style={{ opacity: tip && tip.name !== a.name ? 0.72 : 1 }}
            onMouseEnter={(e) => { const b = wrapRef.current?.getBoundingClientRect(); if (b) setTip({ ...a, x: e.clientX - b.left, y: e.clientY - b.top }); }}
            onMouseMove={(e) => { const b = wrapRef.current?.getBoundingClientRect(); if (b) setTip({ ...a, x: e.clientX - b.left, y: e.clientY - b.top }); }}
          />
        ))}
      </svg>
      {tip && (
        <div className="pointer-events-none absolute z-20 rounded border border-gray-200 bg-white px-2 py-1 shadow-md text-[11px] leading-tight whitespace-nowrap"
          style={{ left: tip.x, top: tip.y - 8, transform: "translate(-50%, -100%)" }}>
          <span className="font-mono font-semibold">{tip.name}</span>
          <span className="text-gray-500 ml-1.5 tabular-nums">{tip.value} · {Math.round(tip.pct * 100)}%</span>
        </div>
      )}
    </div>
  );
};
