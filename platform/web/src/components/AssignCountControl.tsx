import React from "react";

const fieldClass =
  "h-10 border border-gray-200 rounded-lg bg-white outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-500/10";

interface AssignCountControlProps {
  value: number;
  max: number;
  onChange: (count: number) => void;
  disabled?: boolean;
}

export const AssignCountControl: React.FC<AssignCountControlProps> = ({
  value,
  max,
  onChange,
  disabled = false,
}) => {
  const safeMax = Math.max(0, max);
  const disabledControl = disabled || safeMax <= 0;
  const sliderMax = Math.max(1, safeMax);
  const current = Math.min(Math.max(0, value), sliderMax);

  const setCount = (n: number) => {
    if (disabledControl) return;
    const cap = safeMax > 0 ? safeMax : sliderMax;
    const next = Math.min(cap, Math.max(0, Math.round(n)));
    onChange(next);
  };

  return (
    <div className={`flex items-center gap-2 min-w-0 h-10 ${disabledControl ? "opacity-50 pointer-events-none" : ""}`}>
      <span className="text-xs text-gray-400 w-3 shrink-0 tabular-nums">0</span>
      <input
        type="range"
        min={0}
        max={sliderMax}
        step={1}
        value={current}
        onChange={(e) => setCount(Number(e.target.value))}
        className="assign-range flex-1 min-w-[80px]"
        aria-label="分配数量"
        disabled={disabledControl}
      />
      <span className="text-xs text-gray-400 w-6 shrink-0 text-right tabular-nums">{safeMax || sliderMax}</span>
      <input
        type="number"
        min={0}
        max={safeMax || sliderMax}
        value={current || ""}
        placeholder="0"
        onChange={(e) => setCount(Number(e.target.value))}
        className={`${fieldClass} w-14 px-2 text-sm text-center tabular-nums shrink-0`}
        disabled={disabledControl}
      />
      <span className="text-sm text-gray-500 shrink-0">张</span>
    </div>
  );
};
