import React from "react";

type Props = { counts: Record<string, number>; size?: number; compact?: boolean };

export const ClassCountRadar: React.FC<Props> = ({ counts, size = 220, compact = false }) => {
  const entries = Object.entries(counts || {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (!entries.length) return null;

  const max = Math.max(...entries.map(([, n]) => n), 1);
  const cx = size / 2, cy = size / 2, R = size * 0.38, n = entries.length;
  const angleStep = (2 * Math.PI) / n;

  const points = entries.map(([, v], i) => {
    const a = -Math.PI / 2 + i * angleStep;
    const r = (v / max) * R;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
  const poly = points.map((p) => p.join(",")).join(" ");

  const gridLevels = [0.25, 0.5, 0.75, 1];
  const grids = gridLevels.map((lv) => {
    const gr = lv * R;
    return entries.map((_, i) => {
      const a = -Math.PI / 2 + i * angleStep;
      return [cx + gr * Math.cos(a), cy + gr * Math.sin(a)].join(",");
    }).join(" ");
  });

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {grids.map((gp, i) => <polygon key={i} points={gp} fill="none" stroke="#d1d5db" strokeOpacity={0.3} />)}
        {entries.map((_, i) => {
          const a = -Math.PI / 2 + i * angleStep;
          return <line key={i} x1={cx} y1={cy} x2={cx + R * Math.cos(a)} y2={cy + R * Math.sin(a)} stroke="#d1d5db" strokeOpacity={0.2} />;
        })}
        <polygon points={poly} fill="rgba(37,99,235,0.25)" stroke="#2563eb" strokeWidth={2} />
      </svg>
      {!compact && (
        <div className="flex flex-wrap gap-1 justify-center max-w-xs">
          {entries.map(([name]) => <span key={name} className="text-xs font-mono text-gray-500 truncate max-w-[5rem]" title={name}>{name}</span>)}
        </div>
      )}
    </div>
  );
};
