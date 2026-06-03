// Data catalog types and utilities — ported from Label Studio hsap-platform
export type CatalogReport = Record<string, unknown> & {
  dms?: Record<string, DmsTaskEntry>;
  lane?: Record<string, Record<string, unknown>>;
  projects?: { dms?: { active_packs?: string[] }; lane?: { active_packs?: string[] } };
  _cache?: Record<string, unknown>;
};

export type DmsTaskEntry = {
  type?: string; domain?: string; domain_label?: string; label?: string; nc?: number;
  modes?: Record<string, { label?: string; packs?: DmsPackRow[]; class_counts?: Record<string, number> }>;
  packs?: DmsPackRow[]; class_counts?: Record<string, number>;
};

export type DmsPackRow = {
  name: string; enabled: boolean;
  train_images?: number; val_images?: number; test_images?: number;
  class_counts?: Record<string, number>; bbox_points?: [number, number][];
  total_boxes?: number; label_files?: number; sampled?: boolean;
};

export type SplitCounts = { train: number; val: number; test: number };

export function aggregateSplitCounts(packs: DmsPackRow[]): SplitCounts {
  return packs.reduce((acc, p) => ({
    train: acc.train + (p.train_images || 0),
    val: acc.val + (p.val_images || 0),
    test: acc.test + (p.test_images || 0),
  }), { train: 0, val: 0, test: 0 });
}

export function splitCountsFromPack(pack: DmsPackRow | undefined): SplitCounts {
  if (!pack) return { train: 0, val: 0, test: 0 };
  return { train: pack.train_images || 0, val: pack.val_images || 0, test: pack.test_images || 0 };
}

export function aggregateBboxPoints(packs: DmsPackRow[]): [number, number][] {
  const out: [number, number][] = [];
  for (const p of packs) {
    for (const pt of p.bbox_points || []) {
      if (Array.isArray(pt) && pt.length >= 2) {
        const w = Number(pt[0]), h = Number(pt[1]);
        if (!Number.isNaN(w) && !Number.isNaN(h)) out.push([w, h]);
      }
    }
  }
  return out;
}

export function bboxPointsFromPack(pack: DmsPackRow | undefined): [number, number][] {
  if (!pack?.bbox_points?.length) return [];
  return aggregateBboxPoints([pack]);
}

export function primaryPack(packs: DmsPackRow[]): DmsPackRow | undefined {
  return packs.find((p) => p.enabled) || packs[0];
}

export function isMultiTask(entry: DmsTaskEntry | undefined): boolean {
  if (!entry) return false;
  if (entry.type === "multi") return true;
  return Boolean(entry.modes && Object.keys(entry.modes).length > 0);
}

export function isForwardTask(_id: string, entry: DmsTaskEntry | undefined): boolean {
  return _id === "forward" || entry?.domain === "forward";
}

export function dmsTaskModes(entry: DmsTaskEntry | undefined): string[] {
  if (entry?.modes && Object.keys(entry.modes).length > 0) return Object.keys(entry.modes);
  return [];
}

export function dmsPacks(entry: DmsTaskEntry | undefined, mode: string): DmsPackRow[] {
  if (!entry) return [];
  if (mode && entry.modes?.[mode]?.packs?.length) return entry.modes[mode].packs!;
  return (entry.packs || []) as DmsPackRow[];
}

export function findPackRow(entry: DmsTaskEntry | undefined, packName: string, modeId?: string): DmsPackRow | undefined {
  if (!entry || !packName) return undefined;
  if (modeId && entry.modes?.[modeId]?.packs) {
    const hit = entry.modes[modeId].packs!.find((p) => p.name === packName);
    if (hit) return hit;
  }
  for (const p of entry.packs || []) { if (p.name === packName) return p; }
  for (const mode of Object.values(entry.modes || {})) {
    for (const p of mode.packs || []) { if (p.name === packName) return p; }
  }
  return undefined;
}

export function packTaskKey(task: string, mode?: string): string {
  return mode ? `${task}|${mode}` : task;
}

export function parsePackTaskKey(key: string): { task: string; mode: string } {
  const i = key.indexOf("|");
  if (i < 0) return { task: key, mode: "" };
  return { task: key.slice(0, i), mode: key.slice(i + 1) };
}

export function shouldSplitModesInPackView(entry: DmsTaskEntry | undefined): boolean {
  if (!entry) return false;
  const modes = dmsTaskModes(entry);
  if (modes.length <= 1) return false;
  if (entry.domain === "forward" || isForwardTask("", entry)) return true;
  return modes.every((m) => !m.startsWith("batch_"));
}

export const MODE_LABELS: Record<string, string> = {
  batch_0516: "0516 批次", batch_0417: "0417 批次",
  detect: "粗检测", classify: "细分类",
};

export type PackTreeTask = { id: string; mode?: string; label: string; domain?: string; key: string };
export type DmsPackTreeNode = { pack: string; enabled: boolean; tasks: PackTreeTask[] };
export type DmsBatchTreeNode = { taskId: string; label: string; domain?: string; modes: { id: string; label: string }[] };

export function collectTaskPackNames(entry: DmsTaskEntry | undefined): { name: string; enabled: boolean }[] {
  if (!entry) return [];
  const seen = new Map<string, boolean>();
  const mark = (name: string, enabled: boolean) => { seen.set(name, Boolean(enabled) || Boolean(seen.get(name))); };
  for (const p of entry.packs || []) { if (p.name) mark(p.name, p.enabled); }
  for (const mode of Object.values(entry.modes || {})) {
    for (const p of mode.packs || []) { if (p.name) mark(p.name, p.enabled); }
  }
  return [...seen.entries()].map(([name, enabled]) => ({ name, enabled }))
    .sort((a, b) => { if (a.enabled !== b.enabled) return a.enabled ? -1 : 1; return a.name.localeCompare(b.name); });
}

export function packTreeTasksForEntry(taskId: string, entry: DmsTaskEntry, packName: string): PackTreeTask[] {
  const modes = dmsTaskModes(entry);
  if (!shouldSplitModesInPackView(entry)) {
    return [{ id: taskId, label: entry.label || taskId, domain: entry.domain, key: packTaskKey(taskId) }];
  }
  const rows: PackTreeTask[] = [];
  for (const m of modes) {
    const packs = entry.modes?.[m]?.packs || [];
    if (!packs.some((p) => p.name === packName)) continue;
    const modeLabel = entry.modes?.[m]?.label || MODE_LABELS[m] || m;
    const base = (entry.label || taskId).replace(/·交通标志$/, "").trim();
    rows.push({ id: taskId, mode: m, label: `${base} · ${modeLabel}`, domain: entry.domain, key: packTaskKey(taskId, m) });
  }
  return rows.length ? rows : [{ id: taskId, label: entry.label || taskId, domain: entry.domain, key: packTaskKey(taskId) }];
}

export function groupDmsTasks(dms: CatalogReport["dms"]) {
  const entries = Object.entries(dms || {});
  const forward = entries.filter(([, e]) => isForwardTask("", e));
  const forwardIds = new Set(forward.map(([id]) => id));
  return { cabin: entries.filter(([id, e]) => !forwardIds.has(id) && (e.domain || "dms") === "dms"), forward };
}

export function buildDmsPackTree(cat: CatalogReport | null): DmsPackTreeNode[] {
  if (!cat?.dms) return [];
  const activePacks = new Set(cat.projects?.dms?.active_packs || []);
  const byPack = new Map<string, { enabled: boolean; tasks: PackTreeTask[] }>();
  for (const [taskId, entry] of Object.entries(cat.dms)) {
    for (const { name, enabled } of collectTaskPackNames(entry)) {
      if (!byPack.has(name)) byPack.set(name, { enabled: false, tasks: [] });
      const node = byPack.get(name)!;
      node.enabled = node.enabled || Boolean(enabled) || activePacks.has(name);
      for (const row of packTreeTasksForEntry(taskId, entry, name)) {
        if (!node.tasks.some((t) => t.key === row.key)) node.tasks.push(row);
      }
    }
  }
  return [...byPack.entries()].map(([pack, node]) => ({
    pack, enabled: activePacks.has(pack) || node.enabled,
    tasks: node.tasks.sort((a, b) => a.label.localeCompare(b.label, "zh")),
  })).sort((a, b) => { if (a.enabled !== b.enabled) return a.enabled ? -1 : 1; return a.pack.localeCompare(b.pack); });
}

export function buildDmsBatchTree(cat: CatalogReport | null): DmsBatchTreeNode[] {
  if (!cat?.dms) return [];
  const nodes: DmsBatchTreeNode[] = [];
  const { cabin, forward } = groupDmsTasks(cat.dms);
  for (const [taskId, entry] of [...cabin, ...forward]) {
    const modes = dmsTaskModes(entry);
    if (!modes.length) continue;
    nodes.push({
      taskId, label: entry.label || taskId, domain: entry.domain,
      modes: modes.map((m) => ({ id: m, label: entry.modes?.[m]?.label || MODE_LABELS[m] || m })),
    });
  }
  return nodes;
}

export type CatalogScope = { project: "dms" | "dms-pack" | "lane"; task: string; mode?: string; pack?: string };
export function isDmsCatalogScope(scope: CatalogScope): boolean { return scope.project === "dms" || scope.project === "dms-pack"; }

export function parseCatalogScope(key: string): CatalogScope {
  if (key.startsWith("lane:")) return { project: "lane", task: key.slice(5) };
  const parts = key.split(":");
  if (parts[0] === "dms-pack" && parts.length >= 4) return { project: "dms-pack", pack: parts[1], task: parts[2], mode: parts[3] };
  if (parts[0] === "dms-pack" && parts.length >= 3) return { project: "dms-pack", pack: parts[1], task: parts[2] };
  if (parts[0] === "dms") {
    if (parts.length >= 3) return { project: "dms", task: parts[1], mode: parts[2] };
    return { project: "dms", task: parts[1] || "" };
  }
  return { project: "dms", task: key };
}

export function formatCatalogScope(scope: CatalogScope): string {
  if (scope.project === "lane") return `lane:${scope.task}`;
  if (scope.project === "dms-pack" && scope.pack) {
    if (scope.mode) return `dms-pack:${scope.pack}:${scope.task}:${scope.mode}`;
    return `dms-pack:${scope.pack}:${scope.task}`;
  }
  if (scope.mode) return `dms:${scope.task}:${scope.mode}`;
  return `dms:${scope.task}`;
}

export type CatalogViewKind = "pack" | "batch" | "lane";
export type CatalogUiSelection = { view: CatalogViewKind; pack: string; task: string; mode: string; lanePack: string };

export function packScopeKey(pack: string, task: string, mode?: string): string {
  return formatCatalogScope({ project: "dms-pack", pack, task, mode: mode || undefined });
}
export function batchScopeKey(task: string, mode: string): string {
  return formatCatalogScope({ project: "dms", task, mode });
}
export function laneScopeKey(pack: string): string {
  return formatCatalogScope({ project: "lane", task: pack });
}

export function scopeKeyFromSelection(sel: CatalogUiSelection): string {
  if (sel.view === "lane") return laneScopeKey(sel.lanePack);
  if (sel.view === "batch") return batchScopeKey(sel.task, sel.mode);
  return packScopeKey(sel.pack, sel.task, sel.mode || undefined);
}

export function selectionFromScopeKey(key: string, cat: CatalogReport | null): CatalogUiSelection {
  const scope = parseCatalogScope(key);
  const packTree = buildDmsPackTree(cat);
  const batchTree = buildDmsBatchTree(cat);
  const laneKeys = Object.keys(cat?.lane || {});
  if (scope.project === "lane") {
    return { view: "lane", pack: "", task: "", mode: "", lanePack: laneKeys.includes(scope.task) ? scope.task : laneKeys[0] || scope.task };
  }
  if (scope.project === "dms-pack" && scope.pack && scope.task) {
    const node = packTree.find((p) => p.pack === scope.pack);
    const wantKey = packTaskKey(scope.task, scope.mode);
    const match = node?.tasks.find((t) => t.key === wantKey) || node?.tasks.find((t) => t.id === scope.task && (!scope.mode || t.mode === scope.mode));
    const fallback = node?.tasks[0];
    return { view: "pack", pack: scope.pack, task: match?.id || fallback?.id || scope.task, mode: match?.mode || fallback?.mode || scope.mode || "", lanePack: laneKeys[0] || "" };
  }
  if (scope.project === "dms" && scope.task && scope.mode) {
    const node = batchTree.find((t) => t.taskId === scope.task);
    const modeOk = node?.modes.some((m) => m.id === scope.mode);
    if (!cat) return { view: "batch", pack: "dms_v1", task: scope.task, mode: scope.mode, lanePack: laneKeys[0] || "" };
    return { view: "batch", pack: packTree.find((p) => p.enabled)?.pack || packTree[0]?.pack || "", task: scope.task, mode: modeOk ? scope.mode : node?.modes[0]?.id || scope.mode, lanePack: laneKeys[0] || "" };
  }
  const defaultPack = packTree.find((p) => p.enabled) || packTree[0];
  const defaultTask = defaultPack?.tasks.find((t) => t.id === "dam") || defaultPack?.tasks[0];
  const defaultBatch = batchTree.find((t) => t.taskId === "dam") || batchTree[0];
  return { view: "pack", pack: defaultPack?.pack || "dms_v1", task: defaultTask?.id || "dam", mode: defaultBatch?.modes[0]?.id || "batch_0516", lanePack: laneKeys[0] || "" };
}
