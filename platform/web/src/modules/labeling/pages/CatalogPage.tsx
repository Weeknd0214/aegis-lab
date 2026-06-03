import React, { useEffect, useMemo, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { ClassCountBars } from "@/components/ClassCountBars";
import { ClassCountPie } from "@/components/ClassCountPie";
import { ClassCountRadar } from "@/components/ClassCountRadar";
import { BboxScatter } from "@/components/BboxScatter";
import { SplitCountsBars } from "@/components/SplitCountsBars";
import {
  aggregateBboxPoints, aggregateSplitCounts, bboxPointsFromPack,
  buildDmsPackTree, dmsPacks, dmsTaskModes,
  findPackRow, isDmsCatalogScope, packTaskKey, parseCatalogScope,
  parsePackTaskKey, primaryPack, scopeKeyFromSelection, selectionFromScopeKey,
  splitCountsFromPack, type CatalogReport, type CatalogUiSelection,
  type CatalogViewKind, type DmsPackRow, type DmsTaskEntry,
} from "@/lib/dmsCatalog";

const CHART_SIZE = 152;
const SCOPE_STORAGE_KEY = "hsap.catalog.scope";

type DomainTab = "dms" | "forward" | "lane";
const DOMAIN_TABS: { key: DomainTab; label: string; desc: string }[] = [
  { key: "dms", label: "DMS 舱内", desc: "驾驶员监测数据" },
  { key: "forward", label: "ADAS 前向", desc: "前向感知检测数据" },
  { key: "lane", label: "车道线", desc: "Lane 检测数据" },
];

const ChartCell: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="rounded-lg border border-gray-200 bg-gray-50/40 p-2 flex flex-col min-h-0">
    <p className="text-[11px] text-gray-500 m-0 mb-1 leading-none">{title}</p>
    <div className="flex-1 flex items-center justify-center min-h-[132px] overflow-hidden">{children}</div>
  </div>
);

function readStoredScope(fallback: string): string {
  try { return localStorage.getItem(SCOPE_STORAGE_KEY) || fallback; } catch { return fallback; }
}

export const CatalogPage: React.FC = () => {
  const [cat, setCat] = useState<CatalogReport | null>(null);
  const [dmsDetail, setDmsDetail] = useState<DmsTaskEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [domain, setDomain] = useState<DomainTab>("dms");
  const [subView, setSubView] = useState<CatalogViewKind>("pack");
  const [ui, setUi] = useState<CatalogUiSelection>(() =>
    selectionFromScopeKey(readStoredScope("dms-pack:dms_v1:dam"), null)
  );

  const scopeKey = useMemo(() => scopeKeyFromSelection(ui), [ui]);

  const load = async (refresh = false) => {
    setLoading(true); setErr("");
    try { setCat((await hsapApi.catalog(refresh)) as CatalogReport); }
    catch (e) { setErr(String(e)); }
    setLoading(false);
  };

  const scope = parseCatalogScope(scopeKey);
  const isPackView = scope.project === "dms-pack";

  const loadDmsDetail = async (refresh = false) => {
    if (!isDmsCatalogScope(scope) || !scope.task) return;
    try { setDmsDetail((await hsapApi.catalogDms(scope.task, refresh)) as DmsTaskEntry); }
    catch { setDmsDetail(null); }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (!cat) return; setUi((prev) => { const next = selectionFromScopeKey(scopeKeyFromSelection(prev), cat); return next; }); }, [cat]);
  useEffect(() => { loadDmsDetail(); }, [scopeKey]);
  useEffect(() => { try { localStorage.setItem(SCOPE_STORAGE_KEY, scopeKey); } catch { /* */ } }, [scopeKey]);

  // Filter tasks by domain
  const dmsData = useMemo(() => {
    if (!cat?.dms) return {};
    const filtered: Record<string, DmsTaskEntry> = {};
    for (const [k, v] of Object.entries(cat.dms)) {
      const entry = v as DmsTaskEntry;
      const d = entry.domain || (k === "forward" || k === "adas" ? "forward" : "dms");
      if (d === domain || (domain === "forward" && d === "forward")) {
        filtered[k] = entry;
      }
    }
    return filtered;
  }, [cat, domain]);

  // Build filtered catalog for pack/batch trees
  const filteredCat: CatalogReport | null = useMemo(() => {
    if (!cat) return null;
    return { ...cat, dms: dmsData as Record<string, unknown> } as CatalogReport;
  }, [cat, dmsData]);

  // Full pack tree then filter to only packs relevant to current domain
  const allPackTree = useMemo(() => buildDmsPackTree(filteredCat), [filteredCat]);
  const packTree = useMemo(() => {
    if (domain === "dms") {
      // DMS 舱内: only dms_v1, dms_v2
      return allPackTree.filter((p) => p.pack.startsWith("dms_"));
    } else if (domain === "forward") {
      // ADAS 前向: only adas_v1
      return allPackTree.filter((p) => p.pack.startsWith("adas_"));
    }
    return allPackTree;
  }, [allPackTree, domain]);
  const lanePacks = useMemo(() => Object.keys(cat?.lane || {}).sort(), [cat]);

  // Build task list for current domain
  const taskList = useMemo(() => {
    return Object.entries(dmsData).map(([id, entry]) => ({
      id, label: entry.label || id, domain: entry.domain, nc: entry.nc,
    }));
  }, [dmsData]);

  const activePackNode = packTree.find((p) => p.pack === ui.pack) || packTree[0];
  const packTasks = activePackNode?.tasks || [];

  // Reset selection when domain changes
  useEffect(() => {
    if (!filteredCat) return;
    const tasks = Object.keys(dmsData);
    const laneKeys = Object.keys(cat?.lane || {});
    let defaultScope: string;
    if (domain === "lane") {
      defaultScope = `lane:${laneKeys[0] || ""}`;
    } else if (domain === "forward") {
      const fwdPack = packTree[0]?.pack || "adas_v1";
      const fwdTask = packTree[0]?.tasks?.[0];
      defaultScope = `dms-pack:${fwdPack}:${fwdTask?.id || "adas"}`;
    } else {
      const dmsPack = packTree.find((p) => p.pack === "dms_v1")?.pack || packTree[0]?.pack || "dms_v1";
      defaultScope = `dms-pack:${dmsPack}:dam`;
    }
    setUi(selectionFromScopeKey(readStoredScope(defaultScope), filteredCat));
    setSubView(domain === "lane" ? "lane" : "pack");
  }, [domain, packTree]);

  const setPack = (pack: string) => {
    setUi((prev) => {
      const node = packTree.find((p) => p.pack === pack) || packTree[0];
      const prevKey = packTaskKey(prev.task, prev.mode || undefined);
      const match = node?.tasks.find((t) => t.key === prevKey) || node?.tasks[0];
      return { ...prev, view: "pack" as const, pack: node?.pack || pack, task: match?.id || prev.task, mode: match?.mode || "" };
    });
  };

  const setTaskKey = (taskKey: string) => {
    const { task, mode } = parsePackTaskKey(taskKey);
    setUi((prev) => ({ ...prev, view: "pack" as const, task, mode }));
  };

  // DMS/Forward: use existing data paths
  const taskEntry: DmsTaskEntry | undefined = isDmsCatalogScope(scope) ? dmsDetail || (dmsData[scope.task] as DmsTaskEntry | undefined) : undefined;
  const packRow: DmsPackRow | undefined = isPackView && scope.pack ? findPackRow(taskEntry, scope.pack, scope.mode) : undefined;
  const activePackTask = packTasks.find((t) => t.key === packTaskKey(ui.task, ui.mode || undefined));
  const modePacks = scope.project === "dms" ? dmsPacks(taskEntry, scope.mode || "") : [];
  const tablePacks: DmsPackRow[] = isPackView ? (packRow ? [packRow] : []) : modePacks;

  const classCounts = isPackView ? packRow?.class_counts || {} : (scope.mode && taskEntry?.modes?.[scope.mode]?.class_counts) || taskEntry?.class_counts || primaryPack(modePacks)?.class_counts || modePacks[0]?.class_counts || {};
  const bboxPoints = isPackView ? bboxPointsFromPack(packRow) : aggregateBboxPoints(modePacks);
  const splitCounts = isPackView ? splitCountsFromPack(packRow) : aggregateSplitCounts(modePacks);
  const laneEntry = scope.project === "lane" ? cat?.lane?.[scope.task] : null;

  const selectClass = "mt-1 block w-full min-w-[10rem] rounded-md border border-gray-300 px-3 py-2 text-sm";

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>数据目录</h1>
          <p>按训练包与任务查看统计分布</p>
        </div>
        <Button variant="default" size="small" onClick={() => { load(true); loadDmsDetail(true); }} disabled={loading}>刷新</Button>
      </div>

      {err && <p className="text-red-500 text-sm mb-3">{err}</p>}

      <PageQueryState loading={loading}>
        <>
          {/* Domain tabs */}
          <div className="flex gap-2 mb-4">
            {DOMAIN_TABS.map((tab) => (
              <button key={tab.key} onClick={() => setDomain(tab.key)}
                className={`px-4 py-2 rounded-md text-sm transition-colors ${
                  domain === tab.key ? "bg-blue-700 text-white" : "bg-white border border-gray-300 text-gray-600 hover:bg-gray-50"
                }`}>
                <span className="font-medium">{tab.label}</span>
                <span className="ml-1.5 text-xs opacity-70">{tab.desc}</span>
              </button>
            ))}
          </div>

          {/* DMS / Forward sub-views */}
          {domain !== "lane" && (
            <div className="flex flex-wrap gap-2 mb-4 text-sm">
              <p className="text-xs text-gray-500 m-0 self-center mr-2">视图</p>
              {(["pack", "batch"] as const).map((v) => (
                <button key={v} onClick={() => setSubView(v)}
                  className={`rounded-md border px-3 py-1.5 text-sm ${
                    subView === v ? "border-blue-300 bg-blue-50 text-blue-700" : "border-gray-300 bg-white text-gray-600"
                  }`}>
                  {v === "pack" ? "训练包" : "采集批次"}
                </button>
              ))}
            </div>
          )}

          {/* Pack selector */}
          {domain !== "lane" && subView === "pack" && packTree.length > 0 && (
            <div className="flex flex-wrap gap-3 items-end mb-4">
              <label className="flex-1 min-w-[8rem] text-xs text-gray-500">训练包
                <select className={selectClass} value={ui.pack} onChange={(e) => setPack(e.target.value)}>
                  {packTree.map((p) => <option key={p.pack} value={p.pack}>{p.pack}{p.enabled ? "（启用）" : ""}</option>)}
                </select>
              </label>
              <label className="flex-[1.2] min-w-[10rem] text-xs text-gray-500">任务
                <select className={selectClass} value={packTaskKey(ui.task, ui.mode || undefined)} onChange={(e) => setTaskKey(e.target.value)}>
                  {packTasks.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </label>
            </div>
          )}

          {/* DMS/Forward: Charts */}
          {domain !== "lane" && taskEntry && isDmsCatalogScope(scope) && (
            <div className="rounded-xl border border-gray-200 bg-white p-3 mb-4">
              <div className="flex flex-wrap gap-2 items-center mb-2">
                <span className="text-base font-semibold">{activePackTask?.label || taskEntry.label || scope.task}</span>
                {isPackView && scope.pack && <Badge variant="info">{scope.pack}</Badge>}
                {taskEntry.nc != null && <Badge variant="info">{taskEntry.nc} 类</Badge>}
                {Array.isArray((taskEntry as Record<string, unknown>)?.names) && (
                  <div className="flex flex-wrap gap-1">
                    {((taskEntry as Record<string, unknown>).names as string[]).map((n: string) => (
                      <Badge key={n} variant="default" size="small">{n}</Badge>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-3 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] items-stretch">
                <div className="min-w-0 flex flex-col">
                  <p className="text-[11px] text-gray-500 m-0 mb-1.5">类别分布</p>
                  <ClassCountBars counts={classCounts as Record<string, number>} compact maxBars={14} />
                </div>
                <div className="grid grid-cols-2 gap-2 min-w-0">
                  <ChartCell title="数据划分"><SplitCountsBars counts={splitCounts} height={100} /></ChartCell>
                  <ChartCell title="类别占比"><ClassCountPie counts={classCounts as Record<string, number>} size={CHART_SIZE} /></ChartCell>
                  <ChartCell title="框宽高散点"><BboxScatter points={bboxPoints} size={CHART_SIZE} compact /></ChartCell>
                  <ChartCell title="雷达"><ClassCountRadar counts={classCounts as Record<string, number>} size={CHART_SIZE} compact /></ChartCell>
                </div>
              </div>
            </div>
          )}

          {/* Lane */}
          {domain === "lane" && laneEntry && (
            <div className="rounded-xl border border-gray-200 bg-white p-4 mb-4">
              <div className="font-mono text-base font-semibold">{scope.task}</div>
              <p className="text-sm text-gray-500 mt-2">train_lines: {String(laneEntry.train_lines ?? "—")}</p>
            </div>
          )}

          {/* Empty state */}
          {domain !== "lane" && !taskEntry && (
            <div className="card text-center py-12 text-gray-400">
              <p className="text-lg mb-2">暂无 {DOMAIN_TABS.find((t) => t.key === domain)?.label} 数据</p>
              <p className="text-sm">请先在送标工作台中扫描入库，或检查数据集链接是否正确</p>
            </div>
          )}
          {domain === "lane" && !laneEntry && (
            <div className="card text-center py-12 text-gray-400">
              <p className="text-lg mb-2">暂无车道线数据</p>
            </div>
          )}

          {/* Pack table */}
          {domain !== "lane" && isDmsCatalogScope(scope) && taskEntry && tablePacks.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <table className="w-full text-sm">
                <thead><tr className="bg-gray-50 text-left border-b border-gray-200"><th className="px-4 py-2">训练包</th><th>启用</th><th>train</th><th>val</th><th>test</th></tr></thead>
                <tbody>
                  {tablePacks.map((p) => (
                    <tr key={p.name} className="border-b border-gray-100">
                      <td className="px-4 py-2 font-mono">{p.name}</td><td>{p.enabled ? "是" : "否"}</td>
                      <td>{p.train_images ?? "—"}</td><td>{p.val_images ?? "—"}</td><td>{p.test_images ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      </PageQueryState>
    </div>
  );
};
