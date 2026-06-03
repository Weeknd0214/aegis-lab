export const CHART_EMPTY_HINT = "暂无统计，请点刷新重建 catalog 缓存";

export function sortedCountEntries(counts: Record<string, number>, max = 12): [string, number][] {
  return Object.entries(counts || {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, max);
}

export function pieSlices(entries: [string, number][]): { name: string; value: number; pct: number }[] {
  const total = entries.reduce((s, [, n]) => s + n, 0);
  if (total <= 0) return [];
  return entries.map(([name, value]) => ({ name, value, pct: value / total }));
}

export function buildDensityGrid(
  points: [number, number][],
  bins = 16,
): { grid: number[][]; max: number } {
  const grid = Array.from({ length: bins }, () => Array(bins).fill(0));
  let max = 0;
  for (const [w, h] of points) {
    if (w == null || h == null || Number.isNaN(w) || Number.isNaN(h)) continue;
    const wi = Math.min(bins - 1, Math.max(0, Math.floor(w * bins)));
    const hi = Math.min(bins - 1, Math.max(0, Math.floor(h * bins)));
    grid[hi][wi] += 1;
    max = Math.max(max, grid[hi][wi]);
  }
  return { grid, max };
}
